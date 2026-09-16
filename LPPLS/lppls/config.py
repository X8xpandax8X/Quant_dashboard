"""User-editable configuration for instruments, events, and LPPLS horizons."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class InstrumentConfig:
    symbol: str
    name: str
    color: str
    group: str = "individual_stock"

    @property
    def key(self) -> str:
        return self.symbol.replace("^", "index-").replace(".", "-").lower()


@dataclass(frozen=True, slots=True)
class ScaleConfig:
    key: str
    weeks: int
    label: str
    color: str
    dash: str


@dataclass(frozen=True, slots=True)
class HistoricalEvent:
    key: str
    label: str
    start: date
    reference: date
    end: date
    color: str


GROUP_MARKET_INDEX = "market_index"
GROUP_SP500_SECTOR = "sp500_sector"
GROUP_INDIVIDUAL_STOCK = "individual_stock"


MARKET_INDICES: tuple[InstrumentConfig, ...] = (
    InstrumentConfig("^GSPC", "S&P 500", "#E45756", GROUP_MARKET_INDEX),
    InstrumentConfig("^IXIC", "NASDAQ Composite", "#4C78A8", GROUP_MARKET_INDEX),
    InstrumentConfig(
        "^DJI", "Dow Jones Industrial Average", "#F2CF5B", GROUP_MARKET_INDEX
    ),
)


# Yahoo Finance's S&P 500 sector-index symbols. These represent the eleven GICS
# sectors directly; they are not individual stocks or ETF proxies.
SP500_SECTORS: tuple[InstrumentConfig, ...] = (
    InstrumentConfig(
        "^SP500-45", "Information Technology", "#4C78A8", GROUP_SP500_SECTOR
    ),
    InstrumentConfig(
        "^SP500-50", "Communication Services", "#B279A2", GROUP_SP500_SECTOR
    ),
    InstrumentConfig(
        "^SP500-25", "Consumer Discretionary", "#F58518", GROUP_SP500_SECTOR
    ),
    InstrumentConfig("^SP500-30", "Consumer Staples", "#54A24B", GROUP_SP500_SECTOR),
    InstrumentConfig("^SP500-40", "Financials", "#E45756", GROUP_SP500_SECTOR),
    InstrumentConfig("^SP500-35", "Health Care", "#72B7B2", GROUP_SP500_SECTOR),
    InstrumentConfig("^SP500-20", "Industrials", "#9D755D", GROUP_SP500_SECTOR),
    InstrumentConfig("^GSPE", "Energy", "#B79A14", GROUP_SP500_SECTOR),
    InstrumentConfig("^SP500-15", "Materials", "#FF9DA6", GROUP_SP500_SECTOR),
    InstrumentConfig("^SP500-55", "Utilities", "#79706E", GROUP_SP500_SECTOR),
    InstrumentConfig("^SP500-60", "Real Estate", "#D37295", GROUP_SP500_SECTOR),
)


INDIVIDUAL_STOCKS: tuple[InstrumentConfig, ...] = (
    InstrumentConfig("CSCO", "Cisco", "#7B61FF", GROUP_INDIVIDUAL_STOCK),
    InstrumentConfig("INTC", "Intel", "#2196F3", GROUP_INDIVIDUAL_STOCK),
    InstrumentConfig("MSFT", "Microsoft", "#4CAF50", GROUP_INDIVIDUAL_STOCK),
    InstrumentConfig("NVDA", "NVIDIA", "#76B900", GROUP_INDIVIDUAL_STOCK),
    InstrumentConfig("AMD", "AMD", "#ED1C24", GROUP_INDIVIDUAL_STOCK),
    InstrumentConfig("MU", "Micron", "#F7A600", GROUP_INDIVIDUAL_STOCK),
    InstrumentConfig("AVGO", "Broadcom", "#CC6677", GROUP_INDIVIDUAL_STOCK),
    InstrumentConfig("MRVL", "Marvell", "#00A896", GROUP_INDIVIDUAL_STOCK),
    InstrumentConfig("AAPL", "Apple", "#B8C4D4", GROUP_INDIVIDUAL_STOCK),
    InstrumentConfig("GOOGL", "Alphabet", "#4285F4", GROUP_INDIVIDUAL_STOCK),
    InstrumentConfig("DUOL", "Duolingo", "#58CC02", GROUP_INDIVIDUAL_STOCK),
    InstrumentConfig("LLY", "Eli Lilly", "#FF6B81", GROUP_INDIVIDUAL_STOCK),
    InstrumentConfig("CAT", "Caterpillar", "#FFCD11", GROUP_INDIVIDUAL_STOCK),
)


# Each symbol appears once. The dashboard selects the relevant group for each view.
INSTRUMENTS: tuple[InstrumentConfig, ...] = (
    MARKET_INDICES + SP500_SECTORS + INDIVIDUAL_STOCKS
)


# These remain model horizons, not separate source-data periods. Every horizon is
# evaluated over the ticker's complete Yahoo Finance history through the latest
# available observation.
SCALES: tuple[ScaleConfig, ...] = (
    ScaleConfig("short", 32, "Short (32 weeks)", "#F7A600", "dot"),
    ScaleConfig("medium", 104, "Medium (104 weeks)", "#2196F3", "dash"),
    ScaleConfig("long", 208, "Long (208 weeks)", "#ED1C24", "solid"),
)


# Context windows are intentionally editable. `reference` is the market turning
# point used by the dashboard's look-back comparison, not a claim that an entire
# event can be reduced to one exact date.
HISTORICAL_EVENTS: tuple[HistoricalEvent, ...] = (
    HistoricalEvent(
        "dotcom",
        "Dot-com cycle",
        date(1995, 1, 1),
        date(2000, 3, 10),
        date(2002, 10, 9),
        "rgba(123, 97, 255, 0.12)",
    ),
    HistoricalEvent(
        "housing_credit",
        "Housing / credit cycle",
        date(2002, 10, 10),
        date(2007, 10, 9),
        date(2009, 3, 9),
        "rgba(237, 28, 36, 0.10)",
    ),
)


DEFAULT_OUTPUT_NAME = "lppls_dashboard.html"
