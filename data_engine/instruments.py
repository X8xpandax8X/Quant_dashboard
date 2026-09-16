"""Instrument metadata and sector names used by the V1 API."""

from __future__ import annotations

MARKETS = (
    {
        "symbol": "^GSPC",
        "name": "S&P 500",
        "currency": "points",
        "exchange": "S&P Dow Jones Indices",
        "timezone": "America/New_York",
    },
    {
        "symbol": "^NDX",
        "name": "NASDAQ-100",
        "currency": "points",
        "exchange": "Nasdaq",
        "timezone": "America/New_York",
    },
    {
        "symbol": "^VIX",
        "name": "CBOE Volatility Index",
        "currency": "points",
        "exchange": "Cboe",
        "timezone": "America/New_York",
    },
    {
        "symbol": "^N225",
        "name": "Nikkei 225",
        "currency": "points",
        "exchange": "Tokyo Stock Exchange",
        "timezone": "Asia/Tokyo",
    },
    {
        "symbol": "^KS200",
        "name": "KOSPI 200",
        "currency": "points",
        "exchange": "Korea Exchange",
        "timezone": "Asia/Seoul",
    },
    {
        "symbol": "^SET.BK",
        "name": "SET Index",
        "currency": "points",
        "exchange": "Stock Exchange of Thailand",
        "timezone": "Asia/Bangkok",
    },
    {
        "symbol": "BTC-USD",
        "name": "Bitcoin / U.S. Dollar",
        "currency": "USD",
        "exchange": "Crypto",
        "timezone": "UTC",
    },
)

MARKET_BY_SYMBOL = {item["symbol"]: item for item in MARKETS}

# Normalize Yahoo-style aliases into canonical GICS sector labels.
GICS_TO_SECTOR = {
    "Information Technology": "Information Technology",
    "Financials": "Financials",
    "Industrials": "Industrials",
    "Communication Services": "Communication Services",
    "Health Care": "Health Care",
    "Consumer Discretionary": "Consumer Discretionary",
    "Energy": "Energy",
    "Consumer Staples": "Consumer Staples",
    "Materials": "Materials",
    "Real Estate": "Real Estate",
    "Utilities": "Utilities",
}

_SECTOR_ALIASES = {
    "information technology": "Information Technology",
    "technology": "Information Technology",
    "financials": "Financials",
    "financial services": "Financials",
    "health care": "Health Care",
    "healthcare": "Health Care",
    "consumer discretionary": "Consumer Discretionary",
    "consumer cyclical": "Consumer Discretionary",
    "consumer staples": "Consumer Staples",
    "consumer defensive": "Consumer Staples",
    "materials": "Materials",
    "basic materials": "Materials",
    "communications": "Communication Services",
    "communication services": "Communication Services",
    "real estate": "Real Estate",
    "utilities": "Utilities",
    "energy": "Energy",
    "industrials": "Industrials",
}


def canonical_sector(value: object) -> str:
    """Return the contract sector label, retaining unknown values as ``Unknown``."""
    raw = str(value or "").strip()
    gics = _SECTOR_ALIASES.get(raw.casefold(), raw)
    return GICS_TO_SECTOR.get(gics, "Unknown")
