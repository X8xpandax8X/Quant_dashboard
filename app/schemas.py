from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(min_length=1, max_length=20, pattern=r"^[A-Z0-9.^=-]+$")
    weight_bps: int = Field(ge=0, le=10000, strict=True)


class Positions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    positions: list[Position] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique(self):
        if len({p.symbol for p in self.positions}) != len(self.positions):
            raise ValueError("Each stock may appear only once")
        return self


class PortfolioCreate(Positions):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Give the portfolio a name")
        return value


class PortfolioUpdate(PortfolioCreate):
    revision: int = Field(ge=1)


class PortfolioRecord(PortfolioCreate):
    id: str
    revision: int
    created_at: str
    updated_at: str


class PortfolioList(BaseModel):
    items: list[PortfolioRecord]


class User(BaseModel):
    id: str
    email: str
    name: str


class AuthResponse(BaseModel):
    user: User
    csrf_token: str
    mode: Literal["demo", "research", "production"]


class Metadata(BaseModel):
    source: str
    as_of: str | None = None
    retrieved_at: str | None = None
    status: Literal["fresh", "stale", "partial", "unavailable", "demo"]
    requested_window: str | None = None
    actual_start: str | None = None
    actual_end: str | None = None
    currency: str | None = None
    interval: str | None = None
    sample_count: int | None = None
    notes: list[str] = Field(default_factory=list)


class Instrument(BaseModel):
    symbol: str
    name: str
    sector: str | None = None
    currency: str = "USD"
    exchange: str | None = None
    timezone: str | None = None


class Bar(BaseModel):
    time: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None


class PriceResponse(BaseModel):
    instrument: Instrument
    bars: list[Bar]
    last_price: float | None = None
    change: float | None = None
    meta: Metadata


class MarketResponse(BaseModel):
    items: list[PriceResponse]
    timeframe: str


class UniverseResponse(BaseModel):
    items: list[Instrument]
    source: str
    as_of: str | None = None


class Point(BaseModel):
    time: str
    value: float | None


class HistogramBin(BaseModel):
    low: float
    high: float
    count: int


class Distribution(BaseModel):
    daily_mean: float | None
    daily_volatility: float | None
    annual_return: float | None
    annual_volatility: float | None
    win_rate: float | None
    sample_count: int
    returns: list[Point]
    histogram: list[HistogramBin]
    notes: list[str]


class VolumeBin(BaseModel):
    low: float
    high: float
    volume: float


class VolumeProfile(BaseModel):
    poc: float | None
    vah: float | None
    val: float | None
    coverage: float | None
    total_volume: float | None
    bins: list[VolumeBin]
    notes: list[str]


class Series(BaseModel):
    symbol: str
    points: list[Point]


class Correlation(BaseModel):
    x: str
    y: str
    value: float | None
    sample_count: int


class Comparison(BaseModel):
    symbols: list[str]
    series: list[Series]
    correlations: list[Correlation]
    notes: list[str]


class CAPM(BaseModel):
    beta: float | None
    risk_free_rate: float | None
    market_return: float | None
    actual_return: float | None
    expected_return: float | None
    alpha: float | None
    current_price: float | None
    scenario_price: float | None
    sample_count: int
    notes: list[str]


class AnalyticsResponse(BaseModel):
    symbol: str
    distribution: Distribution
    volume_profile: VolumeProfile
    comparison: Comparison
    capm: CAPM
    meta: Metadata


class FundamentalMetrics(BaseModel):
    price: float | None = None
    market_cap: float | None = None
    pe: float | None = None
    pb: float | None = None
    eps: float | None = None
    beta: float | None = None
    sharpe_6m: float | None = None
    capm_target: float | None = None


class Quarter(BaseModel):
    period: str
    revenue: float | None = None
    eps: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    cogs: float | None = None
    opex: float | None = None
    taxes: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    revenue_qoq: float | None = None
    revenue_yoy: float | None = None
    eps_qoq: float | None = None
    eps_yoy: float | None = None


class Estimate(BaseModel):
    period: str
    revenue: float | None = None
    eps: float | None = None


class StatementRow(BaseModel):
    label: str
    value: float | None
    unit: Literal["currency", "number", "ratio", "percent"]


class Statements(BaseModel):
    valuation: list[StatementRow]
    income: list[StatementRow]
    balance_cashflow: list[StatementRow]


class Consensus(BaseModel):
    buy: float | None = None
    hold: float | None = None
    sell: float | None = None
    target_low: float | None = None
    target_mean: float | None = None
    target_high: float | None = None
    analyst_count: int | None = None


class FlowLink(BaseModel):
    source: str
    target: str
    value: float


class FlowStep(BaseModel):
    label: str
    value: float | None


class IncomeFlow(BaseModel):
    kind: Literal["sankey", "waterfall", "unavailable"]
    nodes: list[str]
    links: list[FlowLink]
    steps: list[FlowStep]
    notes: list[str]


class FundamentalsResponse(BaseModel):
    symbol: str
    metrics: FundamentalMetrics
    quarters: list[Quarter]
    estimate: Estimate | None
    statements: Statements
    consensus: Consensus
    income_flow: IncomeFlow
    meta: Metadata


class PortfolioMetrics(BaseModel):
    expected_return: float | None
    volatility: float | None
    sharpe: float | None
    beta: float | None
    sample_count: int
    notes: list[str]


class PerformancePoint(BaseModel):
    time: str
    portfolio: float
    benchmark: float


class Sector(BaseModel):
    sector: str
    weight_bps: int
    holdings: list[Position]


class PortfolioAnalyticsResponse(BaseModel):
    metrics: PortfolioMetrics
    performance: list[PerformancePoint]
    sectors: list[Sector]
    meta: Metadata
