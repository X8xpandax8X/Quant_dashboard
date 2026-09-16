"""Deterministic demo data, explicitly separate from research provider results."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

DEMO_AS_OF = datetime(2026, 9, 14, 20, 0, tzinfo=timezone.utc)


def _seed(symbol: str, purpose: str = "prices") -> int:
    digest = hashlib.sha256(f"quant-stock-v1|{purpose}|{symbol.upper()}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _base_price(symbol: str) -> float:
    markets={"^GSPC":5600,"^NDX":19500,"^VIX":19,"^N225":39000,"^KS200":350,"^SET.BK":1400,"BTC-USD":65000}
    if symbol in markets:
        return float(markets[symbol])
    return 25.0 + (_seed(symbol, "base") % 42500) / 100


def demo_history(symbol: str, interval: str) -> pd.DataFrame:
    """Produce stable, plausible OHLCV bars for any symbol without network access."""
    symbol = symbol.upper()
    intraday = interval in {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"}
    if intraday:
        # Five separate illustrative exchange sessions; do not imply overnight US trading.
        count=13 if interval == "30m" else 78
        frequency="30min" if interval == "30m" else "5min"
        dates=pd.bdate_range(end=DEMO_AS_OF.date(),periods=5)
        index=pd.DatetimeIndex([] ,tz="UTC")
        for day in dates:
            start=pd.Timestamp(day.date()).tz_localize("America/New_York")+pd.Timedelta(hours=9,minutes=30)
            index=index.append(pd.date_range(start,periods=count,freq=frequency).tz_convert("UTC"))
    else:
        index = pd.bdate_range(end=DEMO_AS_OF.date(), periods=270, tz="UTC")
    rng = np.random.default_rng(_seed(symbol, "intraday" if intraday else "daily"))
    drift = ((_seed(symbol, "drift") % 1601) - 700) / 1_000_000
    volatility = 0.004 + (_seed(symbol, "vol") % 650) / 100_000
    returns = rng.normal(drift, volatility, len(index))
    close = _base_price(symbol) * np.exp(np.cumsum(returns))
    if intraday:
        daily=demo_history(symbol,"1d")["close"].tail(6).to_numpy()
        for i in range(5):
            noise=np.cumsum(returns[i*count:(i+1)*count])
            # A bridge joins the previous daily close to this session's close.
            bridge=noise-np.linspace(0,noise[-1],count)
            close[i*count:(i+1)*count]=np.exp(np.linspace(np.log(daily[i]),np.log(daily[i+1]),count)+bridge)
    open_ = np.concatenate(([close[0] * (1 - returns[0] / 3)], close[:-1]))
    spread = np.maximum(np.abs(rng.normal(0.0025, 0.001, len(index))), 0.0003)
    high = np.maximum(open_, close) * (1 + spread)
    low = np.minimum(open_, close) * (1 - spread)
    # Indexes commonly have no exchange volume.  Preserve that missingness.
    volume: np.ndarray | list[float]
    if symbol.startswith("^"):
        volume = np.full(len(index), np.nan)
    else:
        volume = rng.integers(150_000, 8_000_000, len(index)).astype(float)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=index
    )


def demo_fundamentals(symbol: str) -> dict[str, Any]:
    """Rich deterministic fundamentals only for explicit demo mode."""
    symbol = symbol.upper()
    rng = np.random.default_rng(_seed(symbol, "fundamentals"))
    base_revenue = 2_000_000_000 + (_seed(symbol, "revenue") % 90_000_000_000)
    gross_margin = 0.30 + (_seed(symbol, "gross") % 3500) / 10_000
    operating_margin = gross_margin - (0.09 + (_seed(symbol, "opex") % 1200) / 10_000)
    net_margin = operating_margin - (0.02 + (_seed(symbol, "tax") % 800) / 10_000)
    periods = pd.period_range("2024Q3", periods=8, freq="Q")
    quarters: list[dict[str, Any]] = []
    revenue = float(base_revenue)
    for i, period in enumerate(periods):
        revenue *= 1 + float(rng.normal(0.025, 0.035))
        gp = revenue * gross_margin
        oi = revenue * operating_margin
        ni = revenue * net_margin
        eps = ni / (500_000_000 + (_seed(symbol, "shares") % 3_000_000_000))
        quarters.append(
            {
                "period": str(period), "revenue": revenue, "eps": eps, "gross_profit": gp,
                "operating_income": oi, "net_income": ni, "cogs": revenue - gp,
                "opex": gp - oi, "taxes": max(oi - ni, 0.0), "gross_margin": gross_margin,
                "operating_margin": operating_margin, "net_margin": net_margin,
                "revenue_qoq": None, "revenue_yoy": None, "eps_qoq": None, "eps_yoy": None,
            }
        )
    _add_growth(quarters)
    last = quarters[-1]
    price = float(demo_history(symbol, "1d")["close"].iloc[-1])
    shares = 500_000_000 + (_seed(symbol, "shares") % 3_000_000_000)
    trailing_eps = sum(q["eps"] for q in quarters[-4:])
    market_cap = price * shares
    target_mean = price * (1.05 + (_seed(symbol, "target") % 30) / 100)
    return {
        "symbol": symbol,
        "metrics": {
            "price": price, "market_cap": market_cap, "pe": price / trailing_eps if trailing_eps else None,
            "pb": 1.2 + (_seed(symbol, "pb") % 700) / 100, "eps": trailing_eps,
            "beta": 0.65 + (_seed(symbol, "beta") % 130) / 100, "sharpe_6m": None, "capm_target": None,
        },
        "quarters": quarters,
        "estimate": {"period": str(periods[-1] + 1), "revenue": last["revenue"] * 1.035, "eps": last["eps"] * 1.04},
        "statements": {
            "valuation": [{"label": "Market Capitalization", "value": market_cap, "unit": "currency"}, {"label": "Price / Earnings", "value": price / trailing_eps if trailing_eps else None, "unit": "ratio"}],
            "income": [{"label": "Revenue", "value": last["revenue"], "unit": "currency"}, {"label": "Net Income", "value": last["net_income"], "unit": "currency"}],
            "balance_cashflow": [{"label": "Cash", "value": market_cap * 0.08, "unit": "currency"}, {"label": "Free Cash Flow", "value": last["net_income"] * 0.85, "unit": "currency"}],
        },
        "consensus": {"buy": int(5 + _seed(symbol, "buy") % 25), "hold": int(_seed(symbol, "hold") % 14), "sell": int(_seed(symbol, "sell") % 5), "target_low": target_mean * .82, "target_mean": target_mean, "target_high": target_mean * 1.18, "analyst_count": int(8 + _seed(symbol, "analysts") % 35)},
        "income_flow": {
            "kind": "sankey", "nodes": ["Revenue", "COGS", "Gross Profit", "Opex", "Operating Income", "Taxes", "Net Income"],
            "links": [{"source": "Revenue", "target": "COGS", "value": last["cogs"]}, {"source": "Revenue", "target": "Gross Profit", "value": last["gross_profit"]}, {"source": "Gross Profit", "target": "Opex", "value": last["opex"]}, {"source": "Gross Profit", "target": "Operating Income", "value": last["operating_income"]}, {"source": "Operating Income", "target": "Taxes", "value": last["taxes"]}, {"source": "Operating Income", "target": "Net Income", "value": last["net_income"]}],
            "steps": [], "notes": ["Deterministic synthetic data for demo mode."],
        },
    }


def _add_growth(quarters: list[dict[str, Any]]) -> None:
    for i, quarter in enumerate(quarters):
        for field, prefix in (("revenue", "revenue"), ("eps", "eps")):
            for offset, suffix in ((1, "qoq"), (4, "yoy")):
                prior = quarters[i - offset][field] if i >= offset else None
                if prior is None or prior <= 0:
                    quarter[f"{prefix}_{suffix}"] = None
                else:
                    quarter[f"{prefix}_{suffix}"] = quarter[field] / prior - 1
