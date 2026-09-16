from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from lppls.config import (
    GROUP_INDIVIDUAL_STOCK,
    GROUP_MARKET_INDEX,
    GROUP_SP500_SECTOR,
    InstrumentConfig,
)
from lppls.dashboard import build_dashboard, write_dashboard
from lppls.models.lppls import LPPLSFilterConfig
from lppls.types import FitCurve, InstrumentAnalysis, ModelOutput


_DATA_SCRIPT_START = '<script id="dashboard-data" type="application/json">'


def _dashboard_data(html: str) -> dict[str, object]:
    start = html.index(_DATA_SCRIPT_START) + len(_DATA_SCRIPT_START)
    end = html.index("</script>", start)
    return json.loads(html[start:end])


def _instrument_analysis(
    symbol: str,
    name: str,
    color: str,
    group: str,
    *,
    prices: tuple[float, ...] = (100.0, 110.0, 90.0),
    score_values: tuple[float, ...] | None = None,
    parameter_rows: list[dict[str, object]] | None = None,
    fit_curves: list[FitCurve] | None = None,
    diagnostics: dict[str, object] | None = None,
) -> InstrumentAnalysis:
    dates = pd.date_range("2024-01-07", periods=len(prices), freq="W")
    price_series = pd.Series(prices, index=dates, dtype=float, name="close")
    score_values = score_values or tuple(0.25 for _ in dates)
    scores = pd.DataFrame(
        {
            "test": score_values,
            "composite": score_values,
        },
        index=dates,
    )
    output = ModelOutput(
        "test-model",
        "Test Model",
        scores,
        fit_curves=fit_curves or [],
        parameter_rows=parameter_rows or [],
        diagnostics=diagnostics or {},
    )
    return InstrumentAnalysis(
        InstrumentConfig(symbol, name, color, group),
        price_series,
        {"test-model": output},
    )


def _analysis() -> InstrumentAnalysis:
    dates = pd.date_range("2020-01-05", periods=8, freq="W")
    prices = pd.Series(range(10, 18), index=dates, dtype=float, name="close")
    scores = pd.DataFrame(
        {
            "test": [0.0, 0.0, 0.25, 0.25, 0.5, 0.5, 0.75, 0.75],
            "composite": [0.0, 0.0, 0.25, 0.25, 0.5, 0.5, 0.75, 0.75],
        },
        index=dates,
    )
    output = ModelOutput("test-model", "Test Model", scores)
    return InstrumentAnalysis(
        InstrumentConfig(
            "SAFE",
            "Safe <script> label",
            "#123456",
            GROUP_INDIVIDUAL_STOCK,
        ),
        prices,
        {"test-model": output},
    )


def test_dashboard_is_one_offline_document_with_all_sidebar_views() -> None:
    html = build_dashboard([_analysis()], events=())

    assert html.lower().count("<!doctype html>") == 1
    assert html.count('id="dashboard-data"') == 1
    assert "Market overview" in html
    assert "Historical comparison" in html
    assert "Individual stock" in html
    assert "Parameters / diagnostics" in html
    assert "SAFE" in html
    assert "Safe \\u003cscript\\u003e label" in html
    assert "plotly.js" in html.lower()


def test_write_dashboard_creates_only_the_requested_html(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "dashboard.html"

    returned = write_dashboard([_analysis()], output, events=())

    assert returned == output
    assert [path.relative_to(tmp_path) for path in tmp_path.rglob("*.html")] == [
        Path("nested/dashboard.html")
    ]


def test_market_overview_uses_indices_only_and_plots_cumulative_return() -> None:
    market = _instrument_analysis("^GSPC", "S&P 500", "#E45756", GROUP_MARKET_INDEX)
    stock = _instrument_analysis("NVDA", "NVIDIA", "#76B900", GROUP_INDIVIDUAL_STOCK)

    payload = _dashboard_data(build_dashboard([market, stock], events=()))
    figure = payload["figures"]["overview"]["test-model"]
    traces = {trace.get("name"): trace for trace in figure["data"]}

    assert "S&P 500" in traces
    assert not any("NVIDIA" in str(trace.get("name")) for trace in figure["data"])
    assert traces["S&P 500"]["y"] == pytest.approx([0.0, 10.0, -10.0])
    assert figure["layout"]["yaxis"]["title"]["text"] == "Cumulative return (%)"
    assert figure["layout"]["yaxis"]["autorange"] is True
    assert figure["layout"]["xaxis2"]["rangeslider"]["visible"] is True
    assert [item["symbol"] for item in payload["stocks"]["test-model"]] == ["NVDA"]


def test_market_overview_uses_latest_index_start_as_shared_return_baseline() -> None:
    longer = _instrument_analysis(
        "^GSPC",
        "S&P 500",
        "#E45756",
        GROUP_MARKET_INDEX,
        prices=(100.0, 110.0, 90.0),
        score_values=(0.1, 0.2, 0.3),
    )
    shorter = _instrument_analysis(
        "^IXIC",
        "NASDAQ Composite",
        "#4C78A8",
        GROUP_MARKET_INDEX,
        prices=(200.0, 220.0),
        score_values=(0.4, 0.5),
    )
    shifted_dates = shorter.prices.index + pd.Timedelta(weeks=1)
    shorter.prices.index = shifted_dates
    shorter.models["test-model"].score_frame.index = shifted_dates

    payload = _dashboard_data(build_dashboard([longer, shorter], events=()))
    figure = payload["figures"]["overview"]["test-model"]
    traces = {trace.get("name"): trace for trace in figure["data"]}

    assert traces["S&P 500"]["y"] == pytest.approx([0.0, -200 / 11])
    assert traces["NASDAQ Composite"]["y"] == pytest.approx([0.0, 10.0])
    title = figure["layout"]["title"]["text"]
    assert title.startswith("Market overview")
    assert "<br><sup>Shared return baseline: 14/01/2024</sup>" in title
    assert not any(
        "Shared return baseline" in str(annotation.get("text"))
        for annotation in figure["layout"].get("annotations", [])
    )
    assert figure["layout"]["legend"]["orientation"] == "h"
    assert figure["layout"]["legend"]["y"] > 1
    assert figure["layout"]["legend"]["groupclick"] == "togglegroup"

    summary = payload["summary"]["test-model"]
    assert summary["latestComposite"] == pytest.approx(0.4)
    assert summary["asOf"] == "21/01/2024"
    assert [item["symbol"] for item in summary["indices"]] == ["^GSPC", "^IXIC"]
    assert [item["latestScore"] for item in summary["indices"]] == pytest.approx(
        [0.3, 0.5]
    )


def test_index_mean_aligns_different_observation_days_within_calendar_week() -> None:
    monday_series = _instrument_analysis(
        "^GSPC",
        "S&P 500",
        "#E45756",
        GROUP_MARKET_INDEX,
        score_values=(0.1, 0.2, 0.3),
    )
    friday_series = _instrument_analysis(
        "^DJI",
        "Dow Jones Industrial Average",
        "#72B7B2",
        GROUP_MARKET_INDEX,
        score_values=(0.3, 0.4, 0.5),
    )
    friday_series.models["test-model"].score_frame.index -= pd.Timedelta(days=2)

    payload = _dashboard_data(
        build_dashboard([monday_series, friday_series], events=())
    )
    summary = payload["summary"]["test-model"]

    assert summary["latestComposite"] == pytest.approx(0.4)
    assert summary["asOf"] == "21/01/2024"


def test_historical_comparison_contains_indices_and_sp500_sectors_not_stocks() -> None:
    market = _instrument_analysis("^GSPC", "S&P 500", "#E45756", GROUP_MARKET_INDEX)
    sector = _instrument_analysis(
        "^SP500-45",
        "Information Technology",
        "#4C78A8",
        GROUP_SP500_SECTOR,
    )
    stock = _instrument_analysis("NVDA", "NVIDIA", "#76B900", GROUP_INDIVIDUAL_STOCK)

    payload = _dashboard_data(build_dashboard([market, sector, stock], events=()))
    historical = json.dumps(
        payload["figures"]["historical"]["test-model"], ensure_ascii=False
    )

    assert "S&P 500" in historical
    assert "Information Technology" in historical
    assert "NVIDIA" not in historical
    assert payload["figures"]["historical"]["test-model"]["layout"]["coloraxis"][
        "cmin"
    ] == pytest.approx(0.0)
    assert payload["figures"]["historical"]["test-model"]["layout"]["coloraxis"][
        "cmax"
    ] == pytest.approx(1.0)


def test_individual_view_uses_cumulative_return_for_price_and_fit_curve() -> None:
    dates = pd.date_range("2024-01-07", periods=3, freq="W")
    fit = FitCurve(
        key="short",
        label="LPPLS short",
        color="#F7A600",
        dash="dot",
        values=pd.Series([105.0, 120.0], index=dates[1:], dtype=float),
    )
    stock = _instrument_analysis(
        "NVDA",
        "NVIDIA",
        "#76B900",
        GROUP_INDIVIDUAL_STOCK,
        fit_curves=[fit],
    )

    payload = _dashboard_data(build_dashboard([stock], events=()))
    figure = payload["figures"]["individual"]["test-model"]["NVDA"]
    traces = {trace.get("name"): trace for trace in figure["data"]}

    # The adjusted-price series is always the first detail trace; its display
    # label may evolve independently from the numeric return contract.
    assert figure["data"][0]["y"] == pytest.approx([0.0, 10.0, -10.0])
    assert traces["LPPLS short"]["y"] == pytest.approx([5.0, 20.0])
    assert figure["layout"]["yaxis"]["title"]["text"] == "Cumulative return (%)"
    assert figure["layout"]["yaxis"].get("type", "linear") == "linear"
    assert figure["layout"]["yaxis"]["autorange"] is True
    assert figure["layout"]["xaxis3"]["rangeslider"]["visible"] is True
    selector = figure["layout"]["xaxis"]["rangeselector"]
    assert selector["x"] == pytest.approx(1.0)
    assert selector["xanchor"] == "right"
    assert selector["y"] > 1


def test_dashboard_installs_visible_range_y_autoscale_contract() -> None:
    html = build_dashboard([_analysis()], events=())

    for token in (
        'id="index-score-cards"',
        'id="summary-date-note"',
        "plotly_relayout",
        "visiblePrimaryYRange",
        "Plotly.relayout",
        '"yaxis.range"',
    ):
        assert token in html


def test_parameter_table_excludes_stocks_and_links_values_to_filter_rules() -> None:
    rows = [
        {
            "status": "qualified",
            "fit_start": "2026-07-01T00:00:00",
            "fit_end": pd.Timestamp("2026-08-31 12:30:00"),
            "tc_date": "2026-09-15",
            "B": -0.2,
            "m": 0.5,
            "omega": 8.0,
            "damping": 0.9,
            "oscillation_count": 3.0,
            "max_relative_error": 0.1,
            "relative_oscillation_amplitude": 0.08,
            "oscillation_filter_applied": True,
            "passes_b_filter": True,
            "passes_m_filter": False,
            "passes_omega_filter": True,
            "passes_damping_filter": True,
            "passes_oscillation_filter": True,
            "passes_max_relative_error_filter": True,
            "qualified": True,
        }
    ]
    diagnostics = {"qualification_filters": LPPLSFilterConfig().as_dict()}
    market = _instrument_analysis(
        "^GSPC",
        "S&P 500",
        "#E45756",
        GROUP_MARKET_INDEX,
        parameter_rows=rows,
        diagnostics=diagnostics,
    )
    sector = _instrument_analysis(
        "^SP500-45",
        "Information Technology",
        "#4C78A8",
        GROUP_SP500_SECTOR,
        parameter_rows=rows,
        diagnostics=diagnostics,
    )
    stock = _instrument_analysis(
        "NVDA",
        "NVIDIA",
        "#76B900",
        GROUP_INDIVIDUAL_STOCK,
        parameter_rows=rows,
        diagnostics=diagnostics,
    )

    html = build_dashboard([market, sector, stock], events=())
    payload = _dashboard_data(html)
    row = payload["parameters"]["test-model"][0]

    assert [item["Symbol"] for item in payload["parameters"]["test-model"]] == [
        "^GSPC",
        "^SP500-45",
    ]
    assert [item["Symbol"] for item in payload["diagnostics"]["test-model"]] == [
        "^GSPC",
        "^SP500-45",
    ]
    assert row["fit_start"] == "01/07/2026"
    assert row["fit_end"] == "31/08/2026"
    assert row["tc_date"] == "15/09/2026"
    assert row["status"] == "qualified"
    assert "qualified" not in row
    assert payload["instrumentColors"]["NVDA"] == "#76B900"
    assert payload["parameterFilterMap"]["test-model"] == {
        "B": "passes_b_filter",
        "m": "passes_m_filter",
        "omega": "passes_omega_filter",
        "damping": "passes_damping_filter",
        "oscillation_count": "passes_oscillation_filter",
        "max_relative_error": "passes_max_relative_error_filter",
    }
    assert payload["parameterRuleLabels"]["test-model"] == {
        "B": "B < 0",
        "m": "0 < m < 1",
        "omega": "4 ≤ omega ≤ 25",
        "damping": "damping ≥ 0.5",
        "oscillation_count": (
            "oscillation_count ≥ 2.5 when amplitude trigger is active"
        ),
        "relative_oscillation_amplitude": ("activates oscillation rule at ≥ 0.05"),
        "max_relative_error": "max_relative_error ≤ 0.2",
    }
    for css_class in (
        "filter-yes",
        "filter-no",
        "filter-na",
        "status-qualified",
        "status-unqualified",
    ):
        # Once in CSS and once in the table-rendering JavaScript ensures the
        # contract is styled and actually applied, rather than dead metadata.
        assert html.count(css_class) >= 2
    assert "td.qualified-yes" not in html
    assert "td.qualified-no" not in html
