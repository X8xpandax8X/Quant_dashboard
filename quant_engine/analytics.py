"""Daily split-adjusted, dividend-excluding analytics.

No missing prices are filled. Multi-asset prices are aligned on their union of
observed timestamps *before* calculating returns, so gaps cannot be bridged.
Annualization uses 252 trading days and sample covariance/standard deviation.
"""
from __future__ import annotations

import math
from numbers import Integral

import numpy as np
import pandas as pd

ANNUAL_DAYS = 252
MIN_RISK_OBSERVATIONS = 60
BASIS_NOTE = "Split-adjusted price returns exclude dividends; 252 trading days annualization."
RF_NOTE = "Latest annual risk-free yield proxy is held constant over the historical window."
GAP_NOTE = "Missing prices are not filled; only adjacent observed returns are used."


def _number(value):
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _time(value):
    return pd.Timestamp(value).isoformat().replace("+00:00", "Z")


def _clean(frame):
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("History must have a DatetimeIndex")
    if frame.index.has_duplicates or frame.index.hasnans:
        raise ValueError("History timestamps must be unique and present")
    frame = frame.copy().sort_index()
    frame.index = (frame.index.tz_localize("UTC") if frame.index.tz is None
                   else frame.index.tz_convert("UTC"))
    return frame


def _close(frame):
    frame = _clean(frame)
    values = pd.to_numeric(frame["close"], errors="coerce").astype(float)
    return values.where(np.isfinite(values) & (values > 0))


def _returns(frame):
    return _close(frame).pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).dropna()


def _aligned(frames):
    if not frames:
        return pd.DataFrame(), pd.DataFrame()
    prices = pd.concat({key: _close(frame) for key, frame in frames.items()}, axis=1, sort=True).sort_index()
    returns = prices.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).dropna(how="any")
    return prices, returns


def _std(values):
    return _number(values.std(ddof=1)) if len(values) >= 2 else None


def _risk_free(rate):
    value = _number(rate)
    return value if value is not None and value > -1 else None


def _sharpe(returns, risk_free):
    risk_free = _risk_free(risk_free)
    sigma = _std(returns)
    if len(returns) < MIN_RISK_OBSERVATIONS or risk_free is None or sigma is None or sigma <= 1e-12:
        return None
    daily_rf = math.expm1(math.log1p(risk_free) / ANNUAL_DAYS)
    return _number((returns.mean() - daily_rf) / sigma * math.sqrt(ANNUAL_DAYS))


def distribution(frame):
    returns = _returns(frame)
    sigma = _std(returns)
    mean = _number(returns.mean()) if len(returns) else None
    histogram = []
    if len(returns):
        counts, edges = np.histogram(returns.to_numpy(), bins=30)
        histogram = [{"low": _number(edges[i]), "high": _number(edges[i + 1]), "count": int(count)}
                     for i, count in enumerate(counts)]
    notes = [BASIS_NOTE, GAP_NOTE, "Annual return is the arithmetic daily mean multiplied by 252."]
    if len(returns) < 2:
        notes.append("At least two daily returns are required for sample volatility.")
    return {"daily_mean": mean, "daily_volatility": sigma,
            "annual_return": _number(mean * ANNUAL_DAYS) if mean is not None else None,
            "annual_volatility": _number(sigma * math.sqrt(ANNUAL_DAYS)) if sigma is not None else None,
            "win_rate": _number((returns > 0).mean()) if len(returns) else None,
            "sample_count": len(returns),
            "returns": [{"time": _time(t), "value": _number(v)} for t, v in returns.items()],
            "histogram": histogram, "notes": notes}


def volume_profile(frame, bins=50):
    if not isinstance(bins, Integral) or isinstance(bins, bool) or not 1 <= bins <= 1000:
        raise ValueError("bins must be an integer between 1 and 1000")
    frame = _clean(frame)
    prices = frame[["high", "low", "close"]].apply(pd.to_numeric, errors="coerce").astype(float)
    typical = (prices / 3).sum(axis=1, min_count=3)
    volume = pd.to_numeric(frame["volume"], errors="coerce").astype(float)
    valid = (np.isfinite(prices).all(axis=1) & (prices > 0).all(axis=1)
             & np.isfinite(typical) & np.isfinite(volume) & (volume >= 0))
    typical, volume = typical[valid], volume[valid]
    notes = ["Estimated bar-based volume profile: each bar's volume is assigned to (high + low + close) / 3.",
             "Value area expands contiguously from POC to cover at least 70%; ties select the lower-price bin."]
    empty = {"poc": None, "vah": None, "val": None, "coverage": None,
             "total_volume": None, "bins": [], "notes": notes}
    if not len(volume):
        notes.append("No bars have both valid prices and nonnegative observed volume.")
        return empty
    total = _number(volume.sum())
    empty["total_volume"] = total
    if total is None or total <= 0:
        notes.append("Positive finite observed volume is required for a volume profile.")
        return empty
    # Zero-volume bars do not set the traded price range.
    typical, volume = typical[volume > 0], volume[volume > 0]
    if typical.min() == typical.max():
        price = _number(typical.iloc[0])
        return {"poc": price, "vah": price, "val": price, "coverage": 1.0,
                "total_volume": total, "bins": [{"low": price, "high": price, "volume": total}], "notes": notes}
    counts, edges = np.histogram(typical.to_numpy(), bins=int(bins), weights=volume.to_numpy())
    poc = int(np.argmax(counts))
    low = high = poc
    accumulated = counts[poc]
    while accumulated < 0.7 * total and (low > 0 or high < len(counts) - 1):
        left = counts[low - 1] if low > 0 else -1
        right = counts[high + 1] if high < len(counts) - 1 else -1
        if left >= right:
            low -= 1
            accumulated += counts[low]
        else:
            high += 1
            accumulated += counts[high]
    return {"poc": _number(edges[poc] / 2 + edges[poc + 1] / 2), "vah": _number(edges[high + 1]),
            "val": _number(edges[low]), "coverage": _number(accumulated / total), "total_volume": total,
            "bins": [{"low": _number(edges[i]), "high": _number(edges[i + 1]), "volume": _number(v)}
                     for i, v in enumerate(counts)], "notes": notes}


def comparison(frames):
    prices, _ = _aligned(frames)
    common = prices.dropna(how="any")
    series = []
    # All curves begin at the same observed date. Missing later values stay gaps.
    if len(common):
        start = common.index[0]
        for symbol in frames:
            normalized = prices.loc[start:, symbol] / prices.loc[start, symbol] - 1
            series.append({"symbol": symbol, "points": [{"time": _time(t), "value": _number(v)}
                                                         for t, v in normalized.items()]})
    else:
        series = [{"symbol": symbol, "points": []} for symbol in frames]
    correlations = []
    for x in frames:
        for y in frames:
            pair = prices[[x]] if x == y else prices[[x, y]]
            aligned = pair.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).dropna()
            enough = len(aligned) >= MIN_RISK_OBSERVATIONS
            varying = enough and bool((aligned.std(ddof=1) > 1e-12).all())
            value = (1.0 if x == y else _number(aligned[x].corr(aligned[y]))) if varying else None
            correlations.append({"x": x, "y": y, "value": value, "sample_count": len(aligned)})
    notes = [BASIS_NOTE, GAP_NOTE, "Curves use a shared observed baseline; correlations require 60 aligned daily returns and nonzero variance."]
    if not len(common):
        notes.append("No common observed baseline is available.")
    return {"symbols": list(frames), "series": series, "correlations": correlations, "notes": notes}


def capm(frame, benchmark, risk_free):
    _, aligned = _aligned({"asset": frame, "benchmark": benchmark})
    closes = _close(frame).dropna()
    rf = _risk_free(risk_free)
    n = len(aligned)
    market = _number(aligned["benchmark"].mean() * ANNUAL_DAYS) if n else None
    actual = _number(aligned["asset"].mean() * ANNUAL_DAYS) if n else None
    beta = None
    if n >= MIN_RISK_OBSERVATIONS and aligned["benchmark"].std(ddof=1) > 1e-12:
        beta = _number(aligned["asset"].cov(aligned["benchmark"]) / aligned["benchmark"].var(ddof=1))
    expected = _number(rf + beta * (market - rf)) if rf is not None and beta is not None and market is not None else None
    current = _number(closes.iloc[-1]) if len(closes) else None
    scenario = _number(current * (1 + expected)) if current is not None and expected is not None else None
    if scenario is not None and scenario <= 0:
        scenario = None
    notes = [BASIS_NOTE, GAP_NOTE, RF_NOTE,
             "Market and actual annual returns are 252 times aligned arithmetic daily means.",
             "Scenario price is current price times (1 + CAPM return), not a price forecast. Alpha is a realized historical heuristic, not mispricing evidence."]
    if n < MIN_RISK_OBSERVATIONS:
        notes.append("CAPM beta requires at least 60 aligned daily returns.")
    elif beta is None:
        notes.append("Benchmark variance is zero or unavailable; beta is undefined.")
    if rf is None:
        notes.append("Risk-free yield unavailable; expected return, alpha and scenario price are unavailable.")
    return {"beta": beta, "risk_free_rate": rf, "market_return": market, "actual_return": actual,
            "expected_return": expected, "alpha": _number(actual - expected) if actual is not None and expected is not None else None,
            "current_price": current, "scenario_price": scenario, "sample_count": n, "notes": notes}


def sharpe_ratio(frame, risk_free, window=126):
    if not isinstance(window, Integral) or isinstance(window, bool) or window < 1:
        raise ValueError("window must be a positive integer")
    return _sharpe(_returns(frame).tail(window), risk_free)


def portfolio_analysis(frames, weights_bps, benchmark, risk_free):
    if not weights_bps or len(weights_bps) > 30:
        raise ValueError("Portfolio must contain between 1 and 30 unique positions")
    if any(isinstance(w, bool) or not isinstance(w, Integral) or w <= 0 for w in weights_bps.values()):
        raise ValueError("Weights must be positive integer basis points")
    if sum(weights_bps.values()) != 10000:
        raise ValueError("Weights must sum to 10000 basis points")
    if set(weights_bps) - set(frames):
        raise ValueError("Every holding requires a price frame")
    symbols = list(weights_bps)
    # Tuple keys keep the benchmark distinct from any legitimate holding symbol.
    holdings = {(symbol, "holding"): frames[symbol] for symbol in symbols}
    holdings[("benchmark", "reference")] = benchmark
    _, aligned = _aligned(holdings)
    asset = aligned.iloc[:, :len(symbols)]
    market = aligned.iloc[:, -1]
    weights = np.array([weights_bps[s] / 10000 for s in symbols])
    daily = asset.dot(weights)
    n = len(aligned)
    enough = n >= MIN_RISK_OBSERVATIONS
    volatility = beta = None
    if enough:
        covariance = asset.cov(ddof=1).to_numpy()
        variance = float(weights @ covariance @ weights)
        volatility = _number(math.sqrt(max(variance, 0) * ANNUAL_DAYS)) if math.isfinite(variance) else None
        if market.std(ddof=1) > 1e-12:
            beta = _number(sum(weights[i] * asset.iloc[:, i].cov(market) / market.var(ddof=1)
                               for i in range(len(symbols))))
    performance = []
    if n:
        p = (1 + daily).cumprod() - 1
        b = (1 + market).cumprod() - 1
        performance = [{"time": _time(t), "portfolio": _number(p.loc[t]), "benchmark": _number(b.loc[t])}
                       for t in aligned.index]
    notes = [BASIS_NOTE, GAP_NOTE, RF_NOTE,
             "Constant daily rebalanced long-only weights; excludes fees, dividends and taxes.",
             "All metrics use the same complete holding-and-benchmark daily return observations. Performance compounds only these observations; omitted gaps are not modeled.",
             "Expected return is the historical weighted arithmetic daily mean multiplied by 252."]
    if not enough:
        notes.append("Risk metrics require at least 60 aligned daily returns; partial mean and performance are retained.")
    elif beta is None:
        notes.append("Zero or unavailable benchmark variance makes beta undefined.")
    if _risk_free(risk_free) is None:
        notes.append("Risk-free yield unavailable; Sharpe ratio is unavailable.")
    if enough and (_std(daily) or 0) <= 1e-12:
        notes.append("Portfolio return variance is zero; Sharpe ratio is undefined.")
    return {"metrics": {"expected_return": _number(daily.mean() * ANNUAL_DAYS) if n else None,
                        "volatility": volatility, "sharpe": _sharpe(daily, risk_free), "beta": beta,
                        "sample_count": n, "notes": notes}, "performance": performance}
