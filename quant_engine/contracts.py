"""In-memory contracts for pure analytics; all returns/rates are decimal fractions.

History inputs are pandas DataFrames with a unique DatetimeIndex and split-adjusted,
dividend-excluding ``close`` values. Volume profiles additionally require ``high``,
``low`` and ``volume`` on that same price basis. The caller owns adjustment and
exchange-calendar normalization. Explicit missing bars remain missing; analytics
cannot infer an absent exchange session from a single input's timestamps.

Invalid/nonfinite prices become missing observations, never zero or forward-filled
prices. Cross-asset returns align the union of supplied timestamps before computing
changes. Undefined numerical outputs are None so results remain strict JSON.
"""
from collections.abc import Mapping
from typing import TypedDict

import pandas as pd

HistoryFrames = Mapping[str, pd.DataFrame]
WeightsBps = Mapping[str, int]
OptionalNumber = float | None
JSONValue = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]


class TimePoint(TypedDict):
    time: str
    value: OptionalNumber


class HistogramBin(TypedDict):
    low: OptionalNumber
    high: OptionalNumber
    count: int


class DistributionResult(TypedDict):
    daily_mean: OptionalNumber
    daily_volatility: OptionalNumber
    annual_return: OptionalNumber
    annual_volatility: OptionalNumber
    win_rate: OptionalNumber
    sample_count: int
    returns: list[TimePoint]
    histogram: list[HistogramBin]
    notes: list[str]


class VolumeBin(TypedDict):
    low: OptionalNumber
    high: OptionalNumber
    volume: OptionalNumber


class VolumeProfileResult(TypedDict):
    poc: OptionalNumber
    vah: OptionalNumber
    val: OptionalNumber
    coverage: OptionalNumber
    total_volume: OptionalNumber
    bins: list[VolumeBin]
    notes: list[str]


class ComparisonSeries(TypedDict):
    symbol: str
    points: list[TimePoint]


class CorrelationCell(TypedDict):
    x: str
    y: str
    value: OptionalNumber
    sample_count: int


class ComparisonResult(TypedDict):
    symbols: list[str]
    series: list[ComparisonSeries]
    correlations: list[CorrelationCell]
    notes: list[str]


class CAPMResult(TypedDict):
    beta: OptionalNumber
    risk_free_rate: OptionalNumber
    market_return: OptionalNumber
    actual_return: OptionalNumber
    expected_return: OptionalNumber
    alpha: OptionalNumber
    current_price: OptionalNumber
    scenario_price: OptionalNumber
    sample_count: int
    notes: list[str]


class PortfolioMetrics(TypedDict):
    expected_return: OptionalNumber
    volatility: OptionalNumber
    sharpe: OptionalNumber
    beta: OptionalNumber
    sample_count: int
    notes: list[str]


class PerformancePoint(TypedDict):
    time: str
    portfolio: OptionalNumber
    benchmark: OptionalNumber


class PortfolioResult(TypedDict):
    metrics: PortfolioMetrics
    performance: list[PerformancePoint]
