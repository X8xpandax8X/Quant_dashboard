"""Render the complete LPPLS analysis as one offline HTML dashboard.

The dashboard deliberately consumes only the model-neutral result types.  A new
model registered with the analysis engine therefore appears in the model picker
without requiring a second rendering path.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs
from plotly.subplots import make_subplots
from plotly.utils import PlotlyJSONEncoder

from .config import (
    GROUP_INDIVIDUAL_STOCK,
    GROUP_MARKET_INDEX,
    GROUP_SP500_SECTOR,
    HISTORICAL_EVENTS,
    SCALES,
    HistoricalEvent,
)
from .types import InstrumentAnalysis, ModelOutput


__all__ = ["build_dashboard", "write_dashboard"]


_PLOT_CONFIG = {
    "displaylogo": False,
    "responsive": True,
    "scrollZoom": True,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
}

_SCORE_NOTE = (
    "Model score is model-specific. For the built-in LPPLS model, each 0–1 horizon "
    "score is the fraction of its latest scheduled fixed-window fits (8 by default) "
    "that pass every qualification filter: 0 means none passed and 1 means all "
    "passed. Composite is the equal-weight mean of the 32-, 104-, and 208-week "
    "scores when all three are available. It measures recent fit persistence—not "
    "a calibrated probability of a bubble or crash and not the ensemble LPPLS "
    "Confidence Indicator."
)

_QUALIFIED_ESTIMATE_NOTE = (
    "Qualified บนพล็อต LPPLS หมายถึง fit ของหน้าต่างและ horizon นั้นผ่านทุก "
    "filter ที่เปิดใช้ จึงแสดงเส้น LPPLS หรือจุดประมาณ tc ได้ โดยแกน x ของจุดคือ "
    "วันสิ้นสุด fit และแกน y คือจำนวนสัปดาห์จากวันนั้นถึง tc ค่านี้ไม่ได้ยืนยันว่า "
    "จะเกิด bubble หรือ crash และ tc ไม่ใช่วัน crash ที่รับประกัน"
)

_TEMPORAL_PERSISTENCE_NOTE = (
    "temporal_persistence_ratio คือสัดส่วนของ scheduled fits ล่าสุดไม่เกิน 8 "
    "ครั้ง (ค่าเริ่มต้น) ที่ผ่านสถานะ Qualified เช่น ผ่าน 6 จาก 8 ครั้งได้ 0.75 "
    "ค่านี้วัดความต่อเนื่องของสัญญาณเมื่อเลื่อนหน้าต่างเวลา ไม่ใช่ความน่าจะเป็น "
    "ของ bubble/crash และ 8 ครั้งไม่จำเป็นต้องเท่ากับ 8 สัปดาห์; fit ที่คำนวณ "
    "ไม่สำเร็จจะนับเป็นไม่ผ่าน"
)

_FILTER_FIELD_BY_PARAMETER = {
    "B": "passes_b_filter",
    "m": "passes_m_filter",
    "omega": "passes_omega_filter",
    "damping": "passes_damping_filter",
    "oscillation_count": "passes_oscillation_filter",
    "max_relative_error": "passes_max_relative_error_filter",
}

_FALLBACK_COLORS = (
    "#5CC8FF",
    "#C77DFF",
    "#80ED99",
    "#FFD166",
    "#FF6B6B",
    "#4D96FF",
    "#F72585",
    "#B8F2E6",
)


def _clean_series(series: pd.Series) -> pd.Series:
    """Return a finite, chronological numeric series with a datetime index."""

    if series is None or series.empty:
        return pd.Series(dtype=float)
    values = pd.to_numeric(series, errors="coerce")
    index = pd.to_datetime(values.index, errors="coerce", utc=True).tz_convert(None)
    clean = pd.Series(values.to_numpy(dtype=float), index=index)
    clean = clean[~clean.index.isna()]
    clean = clean.replace([np.inf, -np.inf], np.nan).dropna()
    clean = clean[~clean.index.duplicated(keep="last")].sort_index()
    return clean


def _group_analyses(
    analyses: Sequence[InstrumentAnalysis], group: str
) -> list[InstrumentAnalysis]:
    return [analysis for analysis in analyses if analysis.instrument.group == group]


def _cumulative_return(
    prices: pd.Series, *, start: pd.Timestamp | None = None
) -> pd.Series:
    """Cumulative percentage return from the first observation on/after start."""

    clean = _clean_series(prices)
    clean = clean[clean > 0]
    if start is not None:
        clean = clean.loc[clean.index >= pd.Timestamp(start)]
    if clean.empty:
        return pd.Series(dtype=float)
    return clean.div(float(clean.iloc[0])).sub(1.0).mul(100.0)


def _numeric_columns(frame: pd.DataFrame) -> list[Any]:
    if frame is None or frame.empty:
        return []
    return list(frame.select_dtypes(include="number").columns)


def _line_style(column: str, position: int) -> tuple[str, str, float]:
    """Use configured scale styling when possible, then a stable fallback."""

    scale_styles = {scale.key: scale for scale in SCALES}
    if column in scale_styles:
        scale = scale_styles[column]
        return scale.color, scale.dash, 1.7
    if column == "composite":
        return "#F4F7FB", "solid", 3.0
    return _FALLBACK_COLORS[position % len(_FALLBACK_COLORS)], "solid", 1.7


def _event_range(
    event: HistoricalEvent,
) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    return (
        pd.Timestamp(event.start),
        pd.Timestamp(event.reference),
        pd.Timestamp(event.end),
    )


def _add_event_regions(
    figure: go.Figure,
    events: Sequence[HistoricalEvent],
    rows: Sequence[int],
) -> None:
    """Shade known historical contexts without changing the plotted date range."""

    for event in events:
        start, reference, end = _event_range(event)
        for row in rows:
            figure.add_vrect(
                x0=start,
                x1=end,
                fillcolor=event.color,
                opacity=1,
                line_width=0,
                layer="below",
                row=row,
                col=1,
            )
            figure.add_vline(
                x=reference,
                line_color=event.color.replace("0.12", "0.72").replace("0.10", "0.70"),
                line_dash="dot",
                line_width=1,
                row=row,
                col=1,
            )


def _base_layout(figure: go.Figure, *, title: str, height: int) -> None:
    figure.update_layout(
        template="plotly_dark",
        title={"text": title, "x": 0.01, "xanchor": "left"},
        height=height,
        autosize=True,
        hovermode="x unified",
        paper_bgcolor="#10151d",
        plot_bgcolor="#10151d",
        font={
            "family": "-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
            "color": "#dbe5f1",
        },
        legend={
            "orientation": "h",
            "yanchor": "top",
            "y": -0.12,
            "xanchor": "left",
            "x": 0,
            "font": {"size": 11},
        },
        margin={"l": 64, "r": 32, "t": 72, "b": 112},
    )
    figure.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.06)")
    figure.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.06)")


def _available_scores(
    analyses: Sequence[InstrumentAnalysis], model_key: str, *, group: str | None = None
) -> list[tuple[InstrumentAnalysis, pd.Series]]:
    available: list[tuple[InstrumentAnalysis, pd.Series]] = []
    for analysis in analyses:
        if group is not None and analysis.instrument.group != group:
            continue
        output = analysis.models.get(model_key)
        if output is None:
            continue
        score = _clean_series(output.composite_score)
        if not score.empty:
            available.append((analysis, score))
    return available


def _cross_instrument_composite(
    analyses: Sequence[InstrumentAnalysis], model_key: str, *, group: str | None = None
) -> pd.Series:
    value_columns: list[pd.Series] = []
    observation_columns: list[pd.Series] = []
    for analysis, score in _available_scores(analyses, model_key, group=group):
        weekly_bucket = score.index.to_period("W-SUN")
        values = (
            pd.Series(
                score.to_numpy(dtype=float),
                index=weekly_bucket,
                name=analysis.instrument.symbol,
            )
            .groupby(level=0)
            .last()
        )
        observations = (
            pd.Series(
                score.index,
                index=weekly_bucket,
                name=analysis.instrument.symbol,
            )
            .groupby(level=0)
            .last()
        )
        value_columns.append(values)
        observation_columns.append(observations)
    if not value_columns:
        return pd.Series(dtype=float)
    aligned = (
        pd.concat(value_columns, axis=1, join="inner").sort_index().dropna(how="any")
    )
    if aligned.empty:
        return pd.Series(dtype=float)
    observations = pd.concat(observation_columns, axis=1, join="inner").reindex(
        aligned.index
    )
    display_dates = pd.to_datetime(observations.max(axis=1))
    return pd.Series(
        aligned.mean(axis=1).to_numpy(dtype=float),
        index=pd.DatetimeIndex(display_dates),
        name="cross_instrument_composite",
    )


def _overview_figure(
    analyses: Sequence[InstrumentAnalysis],
    model_key: str,
    model_name: str,
    events: Sequence[HistoricalEvent],
) -> go.Figure:
    index_analyses = _group_analyses(analyses, GROUP_MARKET_INDEX)
    available_prices = [
        _clean_series(analysis.prices)
        for analysis in index_analyses
        if model_key in analysis.models and not _clean_series(analysis.prices).empty
    ]
    shared_start = (
        max(series.index.min() for series in available_prices)
        if available_prices
        else None
    )
    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.10,
        row_heights=[0.58, 0.42],
        subplot_titles=(
            "Cumulative return from the shared index start date",
            "LPPLS model score by index and available-index mean",
        ),
    )

    for analysis in index_analyses:
        if model_key not in analysis.models:
            continue
        prices = _clean_series(analysis.prices)
        prices = prices[prices > 0]
        if prices.empty:
            continue
        returns = _cumulative_return(prices, start=shared_start)
        plotted_prices = prices.reindex(returns.index)
        figure.add_trace(
            go.Scatter(
                x=returns.index,
                y=returns,
                mode="lines",
                name=analysis.instrument.name,
                legendgroup=analysis.instrument.symbol,
                line={"color": analysis.instrument.color, "width": 1.7},
                customdata=np.column_stack([plotted_prices.to_numpy()]),
                hovertemplate=(
                    "%{x|%d/%m/%Y}<br>Cumulative return: %{y:,.2f}%"
                    "<br>Index level: %{customdata[0]:,.2f}<extra>%{fullData.name}</extra>"
                ),
            ),
            row=1,
            col=1,
        )

        score = _clean_series(analysis.models[model_key].composite_score)
        if shared_start is not None:
            score = score.loc[score.index >= shared_start]
        if score.empty:
            continue
        figure.add_trace(
            go.Scatter(
                x=score.index,
                y=score,
                mode="lines",
                name=f"{analysis.instrument.name} score",
                legendgroup=analysis.instrument.symbol,
                showlegend=False,
                line={"color": analysis.instrument.color, "width": 1.2},
                opacity=0.55,
                connectgaps=False,
                hovertemplate=(
                    "%{x|%Y-%m-%d}<br>Model score: %{y:.3f}"
                    "<extra>%{fullData.name}</extra>"
                ),
            ),
            row=2,
            col=1,
        )

    composite = _cross_instrument_composite(
        analyses, model_key, group=GROUP_MARKET_INDEX
    )
    if shared_start is not None:
        composite = composite.loc[composite.index >= shared_start]
    if not composite.empty:
        figure.add_trace(
            go.Scatter(
                x=composite.index,
                y=composite,
                mode="lines",
                name="Index mean score",
                line={"color": "#FFFFFF", "width": 3},
                connectgaps=False,
                hovertemplate=(
                    "%{x|%Y-%m-%d}<br>Mean model score: %{y:.3f}"
                    "<extra>Available market indices</extra>"
                ),
            ),
            row=2,
            col=1,
        )

    _add_event_regions(figure, events, rows=(1, 2))
    figure.update_yaxes(
        title_text="Cumulative return (%)", autorange=True, row=1, col=1
    )
    figure.update_yaxes(title_text="Model score", row=2, col=1)
    figure.update_xaxes(
        title_text="Date",
        rangeslider={"visible": True, "thickness": 0.06},
        row=2,
        col=1,
    )
    baseline_label = (
        f"{pd.Timestamp(shared_start):%d/%m/%Y}"
        if shared_start is not None
        else "unavailable"
    )
    title = (
        f"Market overview — {model_name}"
        f"<br><sup>Shared return baseline: {baseline_label}</sup>"
    )
    _base_layout(figure, title=title, height=900)
    figure.update_layout(
        title={
            "text": title,
            "x": 0.01,
            "xanchor": "left",
            "y": 0.985,
            "yanchor": "top",
        },
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.08,
            "xanchor": "left",
            "x": 0,
            "font": {"size": 11},
            "groupclick": "togglegroup",
            "itemclick": "toggle",
            "itemdoubleclick": "toggleothers",
        },
        margin={"l": 64, "r": 32, "t": 160, "b": 105},
    )
    return figure


def _event_window_max(score: pd.Series, event: HistoricalEvent) -> float | None:
    reference = pd.Timestamp(event.reference)
    start = reference - pd.Timedelta(weeks=52)
    window = score.loc[(score.index >= start) & (score.index <= reference)]
    if window.empty:
        return None
    value = float(window.max())
    return value if math.isfinite(value) else None


def _comparison_matrix(
    available: Sequence[tuple[InstrumentAnalysis, pd.Series]],
    events: Sequence[HistoricalEvent],
) -> tuple[list[str], list[str], list[list[float | None]], list[list[str]]]:
    x_labels = [f"{event.label}<br>52w pre-reference" for event in events] + [
        "Most recent<br>52 weeks"
    ]
    y_labels: list[str] = []
    z_values: list[list[float | None]] = []
    text_values: list[list[str]] = []
    for analysis, score in available:
        row = [_event_window_max(score, event) for event in events]
        recent_start = score.index[-1] - pd.Timedelta(weeks=52)
        recent_window = score.loc[score.index >= recent_start]
        latest = float(recent_window.max()) if not recent_window.empty else None
        row.append(latest if latest is not None and math.isfinite(latest) else None)
        y_labels.append(f"{analysis.instrument.name} ({analysis.instrument.symbol})")
        z_values.append(row)
        text_values.append(
            ["N/A" if value is None else f"{value:.2f}" for value in row]
        )
    return x_labels, y_labels, z_values, text_values


def _historical_figure(
    analyses: Sequence[InstrumentAnalysis],
    model_key: str,
    model_name: str,
    events: Sequence[HistoricalEvent],
) -> go.Figure:
    figure = make_subplots(
        rows=3,
        cols=1,
        vertical_spacing=0.12,
        row_heights=[0.25, 0.43, 0.32],
        subplot_titles=(
            "Market indices: maximum LPPLS score in matched 52-week windows",
            "S&P 500 sectors: maximum LPPLS score in matched 52-week windows",
            "Market-index mean score in historical context",
        ),
    )

    groups = (
        (GROUP_MARKET_INDEX, "Market indices", 1),
        (GROUP_SP500_SECTOR, "S&P 500 sectors", 2),
    )
    for group, scope_label, row_number in groups:
        available = _available_scores(analyses, model_key, group=group)
        x_labels, y_labels, z_values, text_values = _comparison_matrix(
            available, events
        )

        if z_values:
            figure.add_trace(
                go.Heatmap(
                    x=x_labels,
                    y=y_labels,
                    z=z_values,
                    text=text_values,
                    texttemplate="%{text}",
                    coloraxis="coloraxis",
                    name=scope_label,
                    hovertemplate=(
                        "%{y}<br>%{x}<br>Model score: %{text}<extra></extra>"
                    ),
                    hoverongaps=False,
                ),
                row=row_number,
                col=1,
            )
        else:
            figure.add_annotation(
                text=f"No {scope_label.lower()} score series is available.",
                showarrow=False,
                x=0.5,
                y=0.5,
                xref=f"x{row_number} domain" if row_number > 1 else "x domain",
                yref=f"y{row_number} domain" if row_number > 1 else "y domain",
            )

    composite = _cross_instrument_composite(
        analyses, model_key, group=GROUP_MARKET_INDEX
    )
    if not composite.empty:
        figure.add_trace(
            go.Scatter(
                x=composite.index,
                y=composite,
                mode="lines",
                name="Available market-index mean",
                line={"color": "#FFFFFF", "width": 2.5},
                connectgaps=False,
                hovertemplate=(
                    "%{x|%Y-%m-%d}<br>Mean model score: %{y:.3f}"
                    "<extra>Available market indices</extra>"
                ),
            ),
            row=3,
            col=1,
        )
    _add_event_regions(figure, events, rows=(3,))
    figure.update_yaxes(automargin=True, row=1, col=1)
    figure.update_yaxes(automargin=True, row=2, col=1)
    figure.update_yaxes(title_text="Model score", row=3, col=1)
    figure.update_xaxes(title_text="Date", row=3, col=1)
    figure.update_layout(
        coloraxis={
            "cmin": 0.0,
            "cmax": 1.0,
            "colorscale": [
                [0.0, "#176b53"],
                [0.5, "#d09b2c"],
                [1.0, "#c63f4f"],
            ],
            "colorbar": {"title": {"text": "Model score"}},
        }
    )
    _base_layout(figure, title=f"Historical comparison — {model_name}", height=1180)
    return figure


def _detail_figure(
    analysis: InstrumentAnalysis,
    output: ModelOutput,
    events: Sequence[HistoricalEvent],
) -> go.Figure:
    figure = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.48, 0.28, 0.24],
        subplot_titles=(
            "Cumulative return and latest qualified fitted curves",
            "Model score series",
            "Qualified model estimates",
        ),
    )
    prices = _clean_series(analysis.prices)
    prices = prices[prices > 0]
    baseline = None if prices.empty else float(prices.iloc[0])
    returns = _cumulative_return(prices)
    if not returns.empty:
        plotted_prices = prices.reindex(returns.index)
        figure.add_trace(
            go.Scatter(
                x=returns.index,
                y=returns,
                mode="lines",
                name="Cumulative return",
                line={"color": analysis.instrument.color, "width": 2.2},
                customdata=np.column_stack([plotted_prices.to_numpy()]),
                hovertemplate=(
                    "%{x|%d/%m/%Y}<br>Cumulative return: %{y:,.2f}%"
                    "<br>Adjusted close: %{customdata[0]:,.2f}<extra></extra>"
                ),
            ),
            row=1,
            col=1,
        )

    for curve in output.fit_curves:
        values = _clean_series(curve.values)
        if values.empty or baseline is None:
            continue
        curve_returns = values.div(baseline).sub(1.0).mul(100.0)
        figure.add_trace(
            go.Scatter(
                x=curve_returns.index,
                y=curve_returns,
                mode="lines",
                name=curve.label,
                line={"color": curve.color, "dash": curve.dash, "width": 2},
                connectgaps=False,
                customdata=np.column_stack([values.to_numpy()]),
                hovertemplate=(
                    "%{x|%d/%m/%Y}<br>Fitted cumulative return: %{y:,.2f}%"
                    "<br>Fitted price: %{customdata[0]:,.2f}"
                    "<extra>%{fullData.name}</extra>"
                ),
            ),
            row=1,
            col=1,
        )

    for position, column in enumerate(_numeric_columns(output.score_frame)):
        series = _clean_series(output.score_frame[column])
        if series.empty:
            continue
        column_label = str(column)
        color, dash, width = _line_style(column_label, position)
        figure.add_trace(
            go.Scatter(
                x=series.index,
                y=series,
                mode="lines",
                name=f"Score: {column_label}",
                line={"color": color, "dash": dash, "width": width},
                connectgaps=False,
                hovertemplate=(
                    "%{x|%Y-%m-%d}<br>Model score: %{y:.3f}"
                    "<extra>%{fullData.name}</extra>"
                ),
            ),
            row=2,
            col=1,
        )

    for position, column in enumerate(_numeric_columns(output.forecast_frame)):
        series = _clean_series(output.forecast_frame[column])
        if series.empty:
            continue
        column_label = str(column)
        color, dash, _ = _line_style(column_label, position)
        figure.add_trace(
            go.Scatter(
                x=series.index,
                y=series,
                mode="markers",
                name=f"Qualified estimate: {column_label}",
                line={"color": color, "dash": dash, "width": 1.7},
                marker={"color": color, "size": 6},
                connectgaps=False,
                hovertemplate="%{x|%Y-%m-%d}<br>Estimate: %{y:.2f}<extra>%{fullData.name}</extra>",
            ),
            row=3,
            col=1,
        )

    if not prices.empty:
        full_range = [prices.index.min(), prices.index.max()]
        figure.update_xaxes(range=full_range)
    _add_event_regions(figure, events, rows=(1, 2, 3))
    figure.update_yaxes(
        title_text="Cumulative return (%)",
        type="linear",
        autorange=True,
        row=1,
        col=1,
    )
    figure.update_yaxes(title_text="Model score", row=2, col=1)
    figure.update_yaxes(
        title_text="Qualified estimate (LPPLS: weeks to tc)", row=3, col=1
    )
    figure.update_xaxes(
        rangeselector={
            "buttons": [
                {"count": 1, "label": "1Y", "step": "year", "stepmode": "backward"},
                {"count": 5, "label": "5Y", "step": "year", "stepmode": "backward"},
                {"step": "all", "label": "All"},
            ],
            "bgcolor": "#17202b",
            "activecolor": "#315f7e",
            "font": {"color": "#dbe5f1"},
            "x": 1,
            "xanchor": "right",
            "y": 1.05,
            "yanchor": "bottom",
        },
        row=1,
        col=1,
    )
    figure.update_xaxes(
        title_text="Date",
        rangeslider={"visible": True, "thickness": 0.06},
        row=3,
        col=1,
    )
    _base_layout(
        figure,
        title=f"{analysis.instrument.name} ({analysis.instrument.symbol}) — {output.model_name}",
        height=1080,
    )
    figure.update_layout(
        title={"y": 0.985, "yanchor": "top"},
        legend={
            "orientation": "h",
            "y": 1.12,
            "yanchor": "bottom",
            "x": 0,
            "xanchor": "left",
        },
        margin={"l": 64, "r": 32, "t": 210, "b": 105},
    )
    return figure


def _figure_payload(figure: go.Figure) -> dict[str, Any]:
    return figure.to_plotly_json()


_TABLE_DATE_FIELDS = frozenset({"fit_start", "fit_end", "tc_date"})


def _display_value(value: Any, *, field: str | None = None) -> str:
    """Turn arbitrary diagnostic values into bounded, safe table text."""

    if value is None:
        return "—"
    if field in _TABLE_DATE_FIELDS:
        try:
            timestamp = pd.Timestamp(value)
        except (TypeError, ValueError, OverflowError):
            timestamp = pd.NaT
        if not pd.isna(timestamp):
            return timestamp.strftime("%d/%m/%Y")
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, (bool, np.bool_)):
        return "Yes" if bool(value) else "No"
    if isinstance(value, (float, np.floating)):
        if not math.isfinite(float(value)):
            return "—"
        return f"{float(value):.6g}"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (Mapping, list, tuple, set)):
        try:
            rendered = json.dumps(
                value, cls=PlotlyJSONEncoder, ensure_ascii=False, sort_keys=True
            )
        except (TypeError, ValueError):
            rendered = repr(value)
        return rendered if len(rendered) <= 500 else rendered[:497] + "..."
    rendered = str(value)
    return rendered if len(rendered) <= 500 else rendered[:497] + "..."


def _reserved_safe_row(
    prefix: Mapping[str, Any], values: Mapping[str, Any]
) -> dict[str, str]:
    row = {
        str(key): _display_value(value, field=str(key)) for key, value in prefix.items()
    }
    for raw_key, value in values.items():
        key = str(raw_key)
        if key in row:
            key = f"Result: {key}"
        row[key] = _display_value(value, field=str(raw_key))
    return row


def _threshold_label(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{numeric:g}" if math.isfinite(numeric) else str(value)


def _qualification_rule_label(parameter: str, rule: Mapping[str, Any]) -> str:
    operator = rule.get("operator")
    if operator == "between_exclusive":
        minimum = _threshold_label(rule.get("minimum"))
        maximum = _threshold_label(rule.get("maximum"))
        return f"{minimum} < {parameter} < {maximum}"
    if operator == "between_inclusive":
        minimum = _threshold_label(rule.get("minimum"))
        maximum = _threshold_label(rule.get("maximum"))
        return f"{minimum} ≤ {parameter} ≤ {maximum}"
    symbol = {"<": "<", ">=": "≥", "<=": "≤"}.get(str(operator))
    if symbol:
        label = f"{parameter} {symbol} {_threshold_label(rule.get('value'))}"
        if parameter == "oscillation_count" and rule.get("precondition"):
            return f"{label} when amplitude trigger is active"
        return label
    return str(rule.get("description") or parameter)


def _parameter_rules_for_model(
    analyses: Sequence[InstrumentAnalysis], model_key: str
) -> tuple[dict[str, str], dict[str, str]]:
    """Expose a model's own qualification thresholds without hard-coding values."""

    for analysis in analyses:
        output = analysis.models.get(model_key)
        if output is None:
            continue
        filters = output.diagnostics.get("qualification_filters")
        if not isinstance(filters, Mapping):
            continue
        filter_map: dict[str, str] = {}
        labels: dict[str, str] = {}
        for parameter, filter_field in _FILTER_FIELD_BY_PARAMETER.items():
            rule = filters.get(parameter)
            if not isinstance(rule, Mapping):
                continue
            filter_map[parameter] = filter_field
            labels[parameter] = _qualification_rule_label(parameter, rule)
        amplitude_rule = filters.get("relative_oscillation_amplitude")
        if isinstance(amplitude_rule, Mapping) and "value" in amplitude_rule:
            labels["relative_oscillation_amplitude"] = (
                "activates oscillation rule at ≥ "
                f"{_threshold_label(amplitude_rule['value'])}"
            )
        return filter_map, labels
    return {}, {}


def _model_catalog(analyses: Sequence[InstrumentAnalysis]) -> list[dict[str, str]]:
    seen: set[str] = set()
    models: list[dict[str, str]] = []
    for analysis in analyses:
        for key, output in analysis.models.items():
            if key in seen:
                continue
            seen.add(key)
            models.append({"key": key, "name": output.model_name})
    return models


def _safe_json(payload: Any) -> str:
    """Serialize JSON for an HTML script-data block without a closing-tag escape."""

    encoded = json.dumps(
        payload,
        cls=PlotlyJSONEncoder,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return (
        encoded.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _dashboard_payload(
    analyses: Sequence[InstrumentAnalysis], events: Sequence[HistoricalEvent]
) -> dict[str, Any]:
    models = _model_catalog(analyses)
    figures: dict[str, dict[str, Any]] = {
        "overview": {},
        "historical": {},
        "individual": {},
    }
    stocks: dict[str, list[dict[str, str]]] = {}
    parameters: dict[str, list[dict[str, str]]] = {}
    diagnostics: dict[str, list[dict[str, str]]] = {}
    summary: dict[str, dict[str, Any]] = {}
    parameter_filter_map: dict[str, dict[str, str]] = {}
    parameter_rule_labels: dict[str, dict[str, str]] = {}
    instrument_colors = {
        analysis.instrument.symbol: analysis.instrument.color for analysis in analyses
    }

    for model in models:
        key = model["key"]
        name = model["name"]
        figures["overview"][key] = _figure_payload(
            _overview_figure(analyses, key, name, events)
        )
        figures["historical"][key] = _figure_payload(
            _historical_figure(analyses, key, name, events)
        )
        figures["individual"][key] = {}
        stocks[key] = []
        parameters[key] = []
        diagnostics[key] = []
        (
            parameter_filter_map[key],
            parameter_rule_labels[key],
        ) = _parameter_rules_for_model(analyses, key)

        for analysis in analyses:
            output = analysis.models.get(key)
            if output is None:
                continue
            symbol = analysis.instrument.symbol
            prices = _clean_series(analysis.prices)
            first_date = None if prices.empty else prices.index[0].strftime("%d/%m/%Y")
            latest_date = (
                None if prices.empty else prices.index[-1].strftime("%d/%m/%Y")
            )
            if analysis.instrument.group == GROUP_INDIVIDUAL_STOCK:
                stocks[key].append(
                    {
                        "symbol": symbol,
                        "name": analysis.instrument.name,
                        "firstDate": first_date or "N/A",
                        "latestDate": latest_date or "N/A",
                    }
                )
                figures["individual"][key][symbol] = _figure_payload(
                    _detail_figure(analysis, output, events)
                )
            common = {
                "Instrument": analysis.instrument.name,
                "Symbol": symbol,
            }
            if analysis.instrument.group in {
                GROUP_MARKET_INDEX,
                GROUP_SP500_SECTOR,
            }:
                for result_row in output.parameter_rows:
                    visible_result = {
                        field: value
                        for field, value in result_row.items()
                        if field != "qualified"
                    }
                    parameters[key].append(_reserved_safe_row(common, visible_result))
                diagnostics[key].append(_reserved_safe_row(common, output.diagnostics))

        composite = _cross_instrument_composite(analyses, key, group=GROUP_MARKET_INDEX)
        index_scores: list[dict[str, Any]] = []
        for analysis in _group_analyses(analyses, GROUP_MARKET_INDEX):
            output = analysis.models.get(key)
            if output is None:
                continue
            score = _clean_series(output.composite_score)
            index_scores.append(
                {
                    "symbol": analysis.instrument.symbol,
                    "name": analysis.instrument.name,
                    "color": analysis.instrument.color,
                    "latestScore": None if score.empty else float(score.iloc[-1]),
                    "asOf": None
                    if score.empty
                    else score.index[-1].strftime("%d/%m/%Y"),
                }
            )
        index_count = sum(
            analysis.instrument.group == GROUP_MARKET_INDEX and key in analysis.models
            for analysis in analyses
        )
        summary[key] = {
            "instrumentCount": index_count,
            "latestComposite": None if composite.empty else float(composite.iloc[-1]),
            "asOf": None
            if composite.empty
            else composite.index[-1].strftime("%d/%m/%Y"),
            "indices": index_scores,
        }

    return {
        "models": models,
        "stocks": stocks,
        "figures": figures,
        "parameters": parameters,
        "diagnostics": diagnostics,
        "summary": summary,
        "parameterFilterMap": parameter_filter_map,
        "parameterRuleLabels": parameter_rule_labels,
        "instrumentColors": instrument_colors,
        "events": [
            {
                "key": event.key,
                "label": event.label,
                "start": event.start.isoformat(),
                "reference": event.reference.isoformat(),
                "end": event.end.isoformat(),
                "color": event.color,
            }
            for event in events
        ],
        "scoreNote": _SCORE_NOTE,
        "qualifiedEstimateNote": _QUALIFIED_ESTIMATE_NOTE,
        "temporalPersistenceNote": _TEMPORAL_PERSISTENCE_NOTE,
        "plotConfig": _PLOT_CONFIG,
    }


_HTML_HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>LPPLS Bubble Analysis Dashboard</title>
<style>
:root {
  --bg: #0b1017;
  --panel: #101721;
  --panel-2: #151e2a;
  --line: #263241;
  --text: #e8eef6;
  --muted: #91a0b3;
  --accent: #58b7e8;
  --sidebar-width: 268px;
}
* { box-sizing: border-box; }
html, body { margin: 0; min-height: 100%; background: var(--bg); color: var(--text); }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
button, select { font: inherit; }
.sidebar {
  position: fixed; inset: 0 auto 0 0; z-index: 30; width: var(--sidebar-width);
  display: flex; flex-direction: column; gap: 20px; overflow-y: auto;
  padding: 24px 18px; background: #0e151e; border-right: 1px solid var(--line);
}
.brand { display: flex; align-items: center; gap: 11px; padding: 0 8px; }
.brand-mark {
  width: 34px; height: 34px; display: grid; place-items: center; border-radius: 9px;
  background: linear-gradient(145deg, #357ca5, #7b61ff); font-weight: 800;
}
.brand strong { display: block; font-size: 15px; letter-spacing: .02em; }
.brand small { color: var(--muted); }
.control label, .nav-label {
  display: block; margin: 0 8px 8px; color: var(--muted); font-size: 11px;
  font-weight: 700; letter-spacing: .09em; text-transform: uppercase;
}
.control select {
  width: 100%; min-height: 40px; padding: 8px 10px; color: var(--text);
  border: 1px solid var(--line); border-radius: 8px; background: var(--panel-2);
}
.nav { display: grid; gap: 5px; }
.nav-button {
  width: 100%; padding: 10px 11px; color: #bdc9d8; text-align: left;
  border: 1px solid transparent; border-radius: 8px; background: transparent; cursor: pointer;
}
.nav-button:hover { color: white; background: #151f2b; }
.nav-button.active { color: white; border-color: #31566d; background: #193044; }
.sidebar-footer { margin-top: auto; padding: 12px 8px 0; color: var(--muted); font-size: 11px; line-height: 1.55; }
.mobile-header { display: none; }
.backdrop { display: none; }
.main { margin-left: var(--sidebar-width); min-width: 0; padding: 28px clamp(16px, 3vw, 42px) 48px; }
.page-head { margin-bottom: 20px; }
.page-head h1 { margin: 0 0 7px; font-size: clamp(23px, 3vw, 34px); font-weight: 650; }
.page-head p { max-width: 900px; margin: 0; color: var(--muted); line-height: 1.55; }
.cards { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 18px 0 8px; }
.card { min-height: 84px; padding: 15px 17px; border: 1px solid var(--line); border-radius: 11px; background: var(--panel); }
.score-card { border-top: 3px solid var(--score-color, var(--accent)); }
.card-label { margin-bottom: 8px; color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .07em; }
.card-value { font-size: 20px; font-weight: 650; }
.card-meta, .summary-note { color: var(--muted); font-size: 11px; line-height: 1.45; }
.card-meta { margin-top: 6px; }
.summary-note { min-height: 18px; margin: 0 2px 16px; }
.notice {
  margin: 16px 0; padding: 12px 15px; color: #c9d7e7; line-height: 1.5;
  border: 1px solid #31566d; border-left: 4px solid var(--accent); border-radius: 8px;
  background: rgba(49, 95, 126, .16);
}
.plot-shell { overflow: hidden; border: 1px solid var(--line); border-radius: 12px; background: var(--panel); }
.plot { width: 100%; min-height: 480px; }
.view[hidden] { display: none !important; }
.view-toolbar { display: flex; flex-wrap: wrap; align-items: end; gap: 14px; margin: 0 0 16px; }
.view-toolbar .control { min-width: min(100%, 320px); }
.event-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; margin: 14px 0 18px; }
.event-card { padding: 12px 14px; border: 1px solid var(--line); border-radius: 9px; background: var(--panel); }
.event-card strong { display: block; margin-bottom: 5px; }
.event-card span { display: block; color: var(--muted); font-size: 12px; line-height: 1.45; }
.table-shell { margin-top: 16px; overflow: auto; max-height: 620px; border: 1px solid var(--line); border-radius: 10px; background: var(--panel); }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { padding: 9px 10px; text-align: left; border-bottom: 1px solid #202b38; white-space: nowrap; }
th { position: sticky; top: 0; z-index: 2; color: #b9c7d8; background: #17212d; }
tr:hover td { background: #141d28; }
tr.instrument-row td:first-child { border-left: 5px solid var(--instrument-color); }
tr.instrument-row td:nth-child(-n+2) { background: var(--instrument-background); }
tr td.filter-yes { background: #f59e0b; color: #111827; font-weight: 750; text-align: center; }
tr td.filter-no { background: #bbf7d0; color: #14532d; font-weight: 750; text-align: center; }
tr td.filter-na { background: #334155; color: #dbe5f1; font-weight: 700; text-align: center; }
tr td.status-qualified { background: #dc2626; color: #ffffff; font-weight: 800; text-align: center; }
tr td.status-unqualified { background: #93c5fd; color: #172554; font-weight: 800; text-align: center; }
tr td.status-neutral { background: #334155; color: #dbe5f1; font-weight: 700; text-align: center; }
.column-rule { display: block; margin-top: 3px; color: #7f91a7; font-size: 10px; font-weight: 500; text-transform: none; }
.status-legend { display: flex; flex-wrap: wrap; gap: 8px 14px; margin: 13px 0; color: var(--muted); font-size: 12px; }
.status-key { display: inline-flex; align-items: center; gap: 6px; }
.status-swatch { width: 13px; height: 13px; border-radius: 3px; border: 1px solid rgba(255,255,255,.28); }
.status-swatch.filter-yes { background: #f59e0b; }
.status-swatch.filter-no { background: #bbf7d0; }
.status-swatch.filter-na { background: #334155; }
.status-swatch.status-qualified { background: #dc2626; }
.status-swatch.status-unqualified { background: #93c5fd; }
.subhead { margin: 28px 0 8px; font-size: 18px; }
.empty { padding: 28px; color: var(--muted); text-align: center; }
@media (max-width: 1100px) {
  .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 760px) {
  .cards { grid-template-columns: 1fr; }
  .mobile-header {
    position: sticky; top: 0; z-index: 25; display: flex; align-items: center; gap: 12px;
    height: 58px; padding: 0 14px; background: rgba(11, 16, 23, .96); border-bottom: 1px solid var(--line);
  }
  .menu-button { padding: 7px 10px; color: var(--text); border: 1px solid var(--line); border-radius: 7px; background: var(--panel-2); }
  .sidebar { transform: translateX(-102%); transition: transform .2s ease; box-shadow: 18px 0 40px rgba(0,0,0,.45); }
  body.sidebar-open .sidebar { transform: translateX(0); }
  body.sidebar-open .backdrop { position: fixed; inset: 0; z-index: 29; display: block; background: rgba(0,0,0,.5); }
  .main { margin-left: 0; padding-top: 22px; }
  .plot { min-height: 420px; }
}
@media print {
  .sidebar, .mobile-header, .backdrop { display: none !important; }
  .main { margin: 0; padding: 0; }
  .view[hidden] { display: none !important; }
}
</style>
<script>"""


_HTML_AFTER_PLOTLY = """</script>
</head>
<body>
<div class="mobile-header">
  <button class="menu-button" id="menu-button" type="button" aria-controls="sidebar" aria-expanded="false">Menu</button>
  <strong>LPPLS Dashboard</strong>
</div>
<div class="backdrop" id="backdrop"></div>
<aside class="sidebar" id="sidebar">
  <div class="brand"><div class="brand-mark">L</div><div><strong>LPPLS Lab</strong><small>Bubble analysis</small></div></div>
  <div class="control">
    <label for="model-selector">Analysis model</label>
    <select id="model-selector" aria-label="Analysis model">"""


_HTML_AFTER_MODEL_OPTIONS = """</select>
  </div>
  <nav class="nav" aria-label="Dashboard views">
    <span class="nav-label">Views</span>
    <button class="nav-button active" type="button" data-view="overview">Market overview</button>
    <button class="nav-button" type="button" data-view="historical">Historical comparison</button>
    <button class="nav-button" type="button" data-view="individual">Individual stock</button>
    <button class="nav-button" type="button" data-view="parameters">Parameters / diagnostics</button>
  </nav>
  <div class="sidebar-footer">Weekly adjusted data from each instrument's first available observation through its latest observation.<br><br>Research signal only; not investment advice.</div>
</aside>
<main class="main">
  <section class="view" id="view-overview">
    <header class="page-head"><h1>Market overview</h1><p>Compare cumulative returns for the S&amp;P 500, NASDAQ Composite, and Dow Jones Industrial Average from their shared display baseline, while every LPPLS fit still uses the instrument's full available raw price history.</p></header>
    <div class="cards" id="index-score-cards"></div>
    <div class="summary-note" id="summary-date-note"></div>
    <div class="notice score-note"></div>
    <div class="plot-shell"><div class="plot" id="overview-plot"></div></div>
  </section>
  <section class="view" id="view-historical" hidden>
    <header class="page-head"><h1>Historical comparison</h1><p>Compare the three market indices and, separately, all 11 S&amp;P 500 GICS sector indices. Each heatmap takes the maximum model score during the 52 weeks ending on an event's configured reference date and compares it with the most recent 52 weeks. Sector history reflects the index provider's available and backfilled series.</p></header>
    <div class="notice score-note"></div>
    <div class="event-grid" id="event-context"></div>
    <div class="plot-shell"><div class="plot" id="historical-plot"></div></div>
  </section>
  <section class="view" id="view-individual" hidden>
    <header class="page-head"><h1>Individual stock</h1><p>Inspect cumulative return from the stock's first available observation, the latest qualified fit curves on the same return baseline, score series, and qualified diagnostic estimates. LPPLS itself continues to fit log adjusted prices. Use 1Y, 5Y, All, or the range slider inside the chart.</p></header>
    <div class="view-toolbar"><div class="control"><label for="stock-selector">Instrument</label><select id="stock-selector"></select></div><div id="stock-range" class="card-value"></div></div>
    <div class="notice score-note"></div>
    <div class="plot-shell"><div class="plot" id="individual-plot"></div></div>
  </section>
  <section class="view" id="view-parameters" hidden>
    <header class="page-head"><h1>Parameters and diagnostics</h1><p>This table shows market indices and S&amp;P 500 sectors only. Individual stocks remain in their dedicated chart and can be added later as sector drill-downs.</p></header>
    <div class="status-legend" aria-label="Parameter status colors">
      <span class="status-key"><span class="status-swatch filter-yes"></span>Filter Yes</span>
      <span class="status-key"><span class="status-swatch filter-no"></span>Filter No</span>
      <span class="status-key"><span class="status-swatch status-qualified"></span>Status: qualified</span>
      <span class="status-key"><span class="status-swatch status-unqualified"></span>Status: unqualified</span>
      <span class="status-key"><span class="status-swatch filter-na"></span>Filter not applied / unavailable</span>
    </div>
    <h2 class="subhead">Latest fit parameters</h2>
    <div class="table-shell" id="parameters-table"></div>
    <h2 class="subhead">Run diagnostics</h2>
    <div class="table-shell" id="diagnostics-table"></div>
  </section>
</main>
<script id="dashboard-data" type="application/json">"""


_HTML_AFTER_DATA = """</script>
<script>
(() => {
  "use strict";
  const state = JSON.parse(document.getElementById("dashboard-data").textContent);
  const modelSelector = document.getElementById("model-selector");
  const stockSelector = document.getElementById("stock-selector");
  let activeView = "overview";

  const hasModels = state.models.length > 0;
  document.querySelectorAll(".score-note").forEach((element) => {
    element.textContent = state.scoreNote;
  });

  function hexToRgba(hex, alpha) {
    const match = /^#([0-9a-f]{6})$/i.exec(hex || "");
    if (!match) return `rgba(88, 183, 232, ${alpha})`;
    const value = Number.parseInt(match[1], 16);
    const red = (value >> 16) & 255;
    const green = (value >> 8) & 255;
    const blue = value & 255;
    return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
  }

  function currentModel() {
    return modelSelector.value || (state.models[0] && state.models[0].key) || "";
  }

  function relayoutXRange(changes) {
    const axisNames = ["xaxis", "xaxis2", "xaxis3"];
    for (const axisName of axisNames) {
      const direct = changes[`${axisName}.range`];
      if (Array.isArray(direct) && direct.length === 2) return direct;
      const start = changes[`${axisName}.range[0]`];
      const end = changes[`${axisName}.range[1]`];
      if (start !== undefined && end !== undefined) return [start, end];
    }
    if (axisNames.some((axisName) => changes[`${axisName}.autorange`] === true)) {
      return [Number.NEGATIVE_INFINITY, Number.POSITIVE_INFINITY];
    }
    return null;
  }

  function dateCoordinate(value) {
    if (typeof value === "number") return value;
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function visiblePrimaryYRange(target, xRange) {
    const start = xRange[0] === Number.NEGATIVE_INFINITY
      ? Number.NEGATIVE_INFINITY
      : dateCoordinate(xRange[0]);
    const end = xRange[1] === Number.POSITIVE_INFINITY
      ? Number.POSITIVE_INFINITY
      : dateCoordinate(xRange[1]);
    if (start === null || end === null) return null;

    const visible = [];
    (target.data || []).forEach((trace) => {
      if ((trace.yaxis || "y") !== "y") return;
      if (trace.visible === false || trace.visible === "legendonly") return;
      const xs = trace.x;
      const ys = trace.y;
      if (!xs || !ys || typeof xs.length !== "number") return;
      const count = Math.min(xs.length, ys.length);
      for (let index = 0; index < count; index += 1) {
        const x = dateCoordinate(xs[index]);
        const y = Number(ys[index]);
        if (x !== null && x >= start && x <= end && Number.isFinite(y)) {
          visible.push(y);
        }
      }
    });
    if (visible.length === 0) return null;
    const minimum = Math.min(...visible);
    const maximum = Math.max(...visible);
    const span = maximum - minimum;
    const padding = span > 0 ? span * 0.08 : Math.max(Math.abs(maximum) * 0.05, 1);
    return [minimum - padding, maximum + padding];
  }

  function removeVisibleYAutoscale(target) {
    const handler = target.__lpplsVisibleYHandler;
    if (handler && typeof target.removeListener === "function") {
      target.removeListener("plotly_relayout", handler);
    }
    target.__lpplsVisibleYHandler = null;
  }

  function installVisibleYAutoscale(target) {
    removeVisibleYAutoscale(target);
    let pendingFrame = null;
    const handler = (changes) => {
      const xRange = relayoutXRange(changes || {});
      if (!xRange) return;
      if (pendingFrame !== null) window.cancelAnimationFrame(pendingFrame);
      pendingFrame = window.requestAnimationFrame(() => {
        pendingFrame = null;
        const yRange = visiblePrimaryYRange(target, xRange);
        if (!yRange) return;
        Plotly.relayout(target, {
          "yaxis.range": yRange,
          "yaxis.autorange": false
        });
      });
    };
    target.on("plotly_relayout", handler);
    target.__lpplsVisibleYHandler = handler;
  }

  function draw(targetId, figure) {
    const target = document.getElementById(targetId);
    if (!figure) {
      removeVisibleYAutoscale(target);
      Plotly.purge(target);
      target.replaceChildren(Object.assign(document.createElement("div"), {
        className: "empty",
        textContent: "No results are available for this selection."
      }));
      return;
    }
    Plotly.react(target, figure.data || [], figure.layout || {}, state.plotConfig)
      .then(() => {
        if (targetId === "overview-plot" || targetId === "individual-plot") {
          installVisibleYAutoscale(target);
        } else {
          removeVisibleYAutoscale(target);
        }
      });
  }

  function scoreCard(label, score, color, asOf, showDate = true) {
    const card = document.createElement("div");
    card.className = "card score-card";
    card.style.setProperty("--score-color", color || "#58b7e8");
    const cardLabel = document.createElement("div");
    cardLabel.className = "card-label";
    cardLabel.textContent = label;
    const cardValue = document.createElement("div");
    cardValue.className = "card-value";
    cardValue.textContent = Number.isFinite(score) ? score.toFixed(3) : "N/A";
    const cardMeta = document.createElement("div");
    cardMeta.className = "card-meta";
    cardMeta.textContent = asOf ? `as of ${asOf}` : "date unavailable";
    card.append(cardLabel, cardValue);
    if (showDate) card.appendChild(cardMeta);
    return card;
  }

  function renderSummary(modelKey) {
    const summary = state.summary[modelKey] || {};
    const cards = document.getElementById("index-score-cards");
    cards.replaceChildren();
    cards.appendChild(
      scoreCard(
        `Latest ${summary.instrumentCount ?? 0}-index mean score`,
        summary.latestComposite,
        "#ffffff",
        summary.asOf,
        false
      )
    );
    (summary.indices || []).forEach((index) => {
      cards.appendChild(
        scoreCard(index.name, index.latestScore, index.color, index.asOf)
      );
    });
    const note = document.getElementById("summary-date-note");
    note.textContent = summary.asOf
      ? `Mean score as of ${summary.asOf}, from the latest weekly bucket shared by all ${summary.instrumentCount ?? 0} available market indices.`
      : "Mean score date is unavailable.";
  }

  function refreshStocks(modelKey) {
    const prior = stockSelector.value;
    stockSelector.replaceChildren();
    const stocks = state.stocks[modelKey] || [];
    stocks.forEach((stock) => {
      const option = document.createElement("option");
      option.value = stock.symbol;
      option.textContent = `${stock.name} (${stock.symbol})`;
      stockSelector.appendChild(option);
    });
    if (stocks.some((stock) => stock.symbol === prior)) stockSelector.value = prior;
    stockSelector.disabled = stocks.length === 0;
    renderStock(modelKey);
  }

  function renderStock(modelKey) {
    const symbol = stockSelector.value;
    const stocks = state.stocks[modelKey] || [];
    const stock = stocks.find((item) => item.symbol === symbol);
    document.getElementById("stock-range").textContent = stock
      ? `${stock.firstDate} → ${stock.latestDate}`
      : "No instrument available";
    const figures = state.figures.individual[modelKey] || {};
    draw("individual-plot", figures[symbol]);
  }

  function renderTable(targetId, rows, useParameterRules = false) {
    const target = document.getElementById(targetId);
    target.replaceChildren();
    if (!rows || rows.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "No rows were reported by this model.";
      target.appendChild(empty);
      return;
    }
    const modelKey = currentModel();
    const filterMap = useParameterRules
      ? (state.parameterFilterMap[modelKey] || {})
      : {};
    const ruleLabels = useParameterRules
      ? (state.parameterRuleLabels[modelKey] || {})
      : {};
    const priority = [
      "Instrument", "Symbol", "model", "scale", "scale_key",
      "horizon_weeks", "status", "fit_start", "fit_end", "tc_date",
      "weeks_to_tc"
    ];
    const allColumns = new Set();
    rows.forEach((row) => Object.keys(row).forEach((key) => allColumns.add(key)));
    allColumns.delete("qualified");
    const filterColumns = [];
    Array.from(allColumns).forEach((column) => {
      if (column.toLowerCase().includes("filter")) {
        allColumns.delete(column);
        filterColumns.push(column);
      }
    });
    const columns = [
      ...priority.filter((key) => allColumns.delete(key)),
      ...Array.from(allColumns),
      ...filterColumns
    ];
    const table = document.createElement("table");
    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");
    columns.forEach((column) => {
      const th = document.createElement("th");
      th.textContent = column;
      const parameter = Object.keys(filterMap).find((key) => filterMap[key] === column);
      const ruleLabel = parameter ? ruleLabels[parameter] : null;
      if (ruleLabel) {
        const rule = document.createElement("span");
        rule.className = "column-rule";
        rule.textContent = `rule: ${ruleLabel}`;
        th.appendChild(rule);
        th.title = `Qualification rule: ${ruleLabel}`;
      }
      headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      const instrumentColor = state.instrumentColors[row.Symbol];
      if (instrumentColor) {
        tr.classList.add("instrument-row");
        tr.style.setProperty("--instrument-color", instrumentColor);
        tr.style.setProperty(
          "--instrument-background",
          hexToRgba(instrumentColor, 0.16)
        );
      }
      columns.forEach((column) => {
        const td = document.createElement("td");
        let value = row[column] ?? "—";
        const oscillationNotApplied =
          row.oscillation_filter_applied === "No" &&
          column === "passes_oscillation_filter";
        if (oscillationNotApplied) value = "N/A";
        td.textContent = value;
        const normalizedColumn = column.toLowerCase();
        if (normalizedColumn === "status") {
          if (value === "qualified") {
            td.classList.add("status-qualified");
          } else if (value === "unqualified") {
            td.classList.add("status-unqualified");
          } else {
            td.classList.add("status-neutral");
          }
        } else if (oscillationNotApplied) {
          td.classList.add("filter-na");
          td.title = "Oscillation-count filter was not applied because its amplitude trigger was inactive.";
        } else if (normalizedColumn.includes("filter") && (value === "Yes" || value === "No")) {
          td.classList.add(value === "Yes" ? "filter-yes" : "filter-no");
        }
        if (column === "relative_oscillation_amplitude" && ruleLabels[column]) {
          const active = row.oscillation_filter_applied === "Yes";
          td.title = `${ruleLabels[column]}; trigger ${active ? "active" : "inactive"}`;
        }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    target.appendChild(table);
  }

  function renderEvents() {
    const target = document.getElementById("event-context");
    target.replaceChildren();
    state.events.forEach((event) => {
      const card = document.createElement("div");
      card.className = "event-card";
      card.style.borderLeft = `4px solid ${event.color}`;
      const title = document.createElement("strong");
      title.textContent = event.label;
      const dates = document.createElement("span");
      dates.textContent = `${event.start} – ${event.end}; reference ${event.reference}`;
      const method = document.createElement("span");
      method.textContent = `Comparison window: 52 weeks through ${event.reference}`;
      card.append(title, dates, method);
      target.appendChild(card);
    });
  }

  function renderActive() {
    const modelKey = currentModel();
    if (!hasModels) {
      ["overview-plot", "historical-plot", "individual-plot"].forEach((id) => draw(id, null));
      renderTable("parameters-table", [], true);
      renderTable("diagnostics-table", []);
      return;
    }
    if (activeView === "overview") {
      renderSummary(modelKey);
      draw("overview-plot", state.figures.overview[modelKey]);
    } else if (activeView === "historical") {
      draw("historical-plot", state.figures.historical[modelKey]);
    } else if (activeView === "individual") {
      renderStock(modelKey);
    } else if (activeView === "parameters") {
      renderTable("parameters-table", state.parameters[modelKey] || [], true);
      renderTable("diagnostics-table", state.diagnostics[modelKey] || []);
    }
  }

  function showView(view) {
    activeView = view;
    document.querySelectorAll(".view").forEach((element) => {
      element.hidden = element.id !== `view-${view}`;
    });
    document.querySelectorAll(".nav-button").forEach((button) => {
      const active = button.dataset.view === view;
      button.classList.toggle("active", active);
      button.setAttribute("aria-current", active ? "page" : "false");
    });
    document.body.classList.remove("sidebar-open");
    document.getElementById("menu-button").setAttribute("aria-expanded", "false");
    renderActive();
    history.replaceState(null, "", `#${view}`);
  }

  document.querySelectorAll(".nav-button").forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.view));
  });
  modelSelector.addEventListener("change", () => {
    refreshStocks(currentModel());
    renderActive();
  });
  stockSelector.addEventListener("change", () => renderStock(currentModel()));
  document.getElementById("menu-button").addEventListener("click", () => {
    const open = document.body.classList.toggle("sidebar-open");
    document.getElementById("menu-button").setAttribute("aria-expanded", String(open));
  });
  document.getElementById("backdrop").addEventListener("click", () => {
    document.body.classList.remove("sidebar-open");
    document.getElementById("menu-button").setAttribute("aria-expanded", "false");
  });

  renderEvents();
  refreshStocks(currentModel());
  const initialView = ["overview", "historical", "individual", "parameters"]
    .includes(location.hash.slice(1)) ? location.hash.slice(1) : "overview";
  showView(initialView);
})();
</script>
</body>
</html>
"""


def build_dashboard(
    analyses: Sequence[InstrumentAnalysis],
    events: Sequence[HistoricalEvent] = HISTORICAL_EVENTS,
) -> str:
    """Build one self-contained HTML document without writing or opening it."""

    analysis_list = tuple(analyses)
    event_list = tuple(events)
    payload = _dashboard_payload(analysis_list, event_list)
    model_options = "".join(
        f'<option value="{escape(model["key"], quote=True)}">'
        f'{escape(model["name"])}'
        f"</option>"
        for model in payload["models"]
    )
    if not model_options:
        model_options = '<option value="">No models available</option>'
    return (
        _HTML_HEAD
        + get_plotlyjs()
        + _HTML_AFTER_PLOTLY
        + model_options
        + _HTML_AFTER_MODEL_OPTIONS
        + _safe_json(payload)
        + _HTML_AFTER_DATA
    )


def write_dashboard(
    analyses: Sequence[InstrumentAnalysis],
    output_path: str | Path,
    events: Sequence[HistoricalEvent] = HISTORICAL_EVENTS,
) -> Path:
    """Write exactly one offline dashboard at ``output_path`` and return its path."""

    path = Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_dashboard(analyses, events), encoding="utf-8")
    return path
