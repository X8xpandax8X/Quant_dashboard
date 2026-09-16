"""Provider-independent fundamentals normalization."""

from __future__ import annotations

from typing import Any, Iterable
import math

import pandas as pd

METRIC_FIELDS = ("price", "market_cap", "pe", "pb", "eps", "beta", "sharpe_6m", "capm_target")
QUARTER_FIELDS = ("period", "revenue", "eps", "gross_profit", "operating_income", "net_income", "cogs", "opex", "taxes", "gross_margin", "operating_margin", "net_margin", "revenue_qoq", "revenue_yoy", "eps_qoq", "eps_yoy")

ALIASES = {
    "revenue": ("Total Revenue", "Operating Revenue", "Revenue"),
    "gross_profit": ("Gross Profit",),
    "operating_income": ("Operating Income", "Operating Income Loss"),
    "net_income": ("Net Income", "Net Income Common Stockholders", "Net Income Including Noncontrolling Interests"),
    "cogs": ("Cost Of Revenue", "Cost of Revenue", "Cost Of Goods And Services Sold"),
    "taxes": ("Tax Provision", "Income Tax Expense"),
    "eps": ("Diluted EPS", "Basic EPS"),
}


def number(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def pick(row: pd.Series, names: Iterable[str]) -> float | None:
    for name in names:
        if name in row.index:
            value = number(row[name])
            if value is not None:
                return value
    return None


def normalize_quarters(income: pd.DataFrame | None) -> tuple[list[dict[str, Any]], list[str]]:
    """Map varying Yahoo statement labels to the contract and retain missing values."""
    notes: list[str] = []
    if income is None or income.empty:
        return [], ["Quarterly income statement unavailable from provider."]
    rows: list[dict[str, Any]] = []
    for period, row in income.T.sort_index().iterrows():
        revenue = pick(row, ALIASES["revenue"])
        gross_profit = pick(row, ALIASES["gross_profit"])
        operating_income = pick(row, ALIASES["operating_income"])
        net_income = pick(row, ALIASES["net_income"])
        cogs = pick(row, ALIASES["cogs"])
        if cogs is None and revenue is not None and gross_profit is not None:
            cogs = revenue - gross_profit
        opex = gross_profit - operating_income if gross_profit is not None and operating_income is not None else None
        taxes = pick(row, ALIASES["taxes"])
        eps = pick(row, ("Diluted EPS", "Basic EPS"))
        rows.append({
            "period": pd.Timestamp(period).to_period("Q").__str__(), "revenue": revenue, "eps": eps,
            "gross_profit": gross_profit, "operating_income": operating_income, "net_income": net_income,
            "cogs": cogs, "opex": opex, "taxes": taxes,
            "gross_margin": _ratio(gross_profit, revenue), "operating_margin": _ratio(operating_income, revenue), "net_margin": _ratio(net_income, revenue),
            "revenue_qoq": None, "revenue_yoy": None, "eps_qoq": None, "eps_yoy": None,
        })
    _add_growth(rows, notes)
    return rows[-8:], notes


def _ratio(value: float | None, denominator: float | None) -> float | None:
    return value / denominator if value is not None and denominator is not None and denominator > 0 else None


def _add_growth(rows: list[dict[str, Any]], notes: list[str]) -> None:
    invalid = False
    for i, row in enumerate(rows):
        for field, prefix in (("revenue", "revenue"), ("eps", "eps")):
            for offset, suffix in ((1, "qoq"), (4, "yoy")):
                previous = rows[i - offset][field] if i >= offset else None
                current = row[field]
                if previous is None or previous <= 0 or current is None:
                    row[f"{prefix}_{suffix}"] = None
                    invalid = invalid or previous is not None and previous <= 0
                else:
                    row[f"{prefix}_{suffix}"] = current / previous - 1
    if invalid:
        notes.append("Growth is null where its prior-period revenue or EPS is zero or negative.")


def income_flow(quarter: dict[str, Any] | None) -> dict[str, Any]:
    unavailable = {"kind": "unavailable", "nodes": [], "links": [], "steps": [], "notes": ["Income statement unavailable."]}
    if not quarter or quarter.get("revenue") is None:
        return unavailable
    revenue, gross, operating, net = (quarter.get(k) for k in ("revenue", "gross_profit", "operating_income", "net_income"))
    cogs, opex, taxes = (quarter.get(k) for k in ("cogs", "opex", "taxes"))
    # Sankey requires nonnegative edge widths and internally consistent totals.
    values = (revenue, gross, operating, net, cogs, opex, taxes)
    reconcilable = all(v is not None and v >= 0 for v in values)
    if reconcilable:
        # All internal nodes must conserve flow, not just revenue.
        reconcilable = all(abs(parent - sum(children)) <= max(0.01, abs(parent) * 1e-6)
                           for parent, children in [(revenue,(gross,cogs)),(gross,(operating,opex)),(operating,(net,taxes))])
    if reconcilable:
        return {"kind": "sankey", "nodes": ["Revenue", "COGS", "Gross Profit", "Opex", "Operating Income", "Taxes", "Net Income"], "links": [{"source": "Revenue", "target": "COGS", "value": cogs}, {"source": "Revenue", "target": "Gross Profit", "value": gross}, {"source": "Gross Profit", "target": "Opex", "value": opex}, {"source": "Gross Profit", "target": "Operating Income", "value": operating}, {"source": "Operating Income", "target": "Taxes", "value": taxes}, {"source": "Operating Income", "target": "Net Income", "value": net}], "steps": [], "notes": []}
    return {"kind": "waterfall", "nodes": [], "links": [], "steps": [{"label": "Revenue", "value": revenue}, {"label": "Gross Profit", "value": gross}, {"label": "Operating Income", "value": operating}, {"label": "Net Income", "value": net}], "notes": ["Waterfall used because statement flows are negative, missing, or do not reconcile for a Sankey chart."]}
