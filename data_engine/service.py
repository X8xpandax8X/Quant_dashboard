"""DataService implementation: deterministic demo data and offline-first research data."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd
import numpy as np

from .cache import CacheStore, iso_now, utc_now
from .contracts import MarketCache
from .freshness import FreshnessPolicy
from .demo import DEMO_AS_OF, demo_fundamentals, demo_history
from .fundamentals import income_flow, normalize_quarters, number
from .instruments import MARKET_BY_SYMBOL, MARKETS, canonical_sector

TIMEFRAMES = {
    "1D": ("5m", "1d", timedelta(minutes=5)),
    "5D": ("30m", "5d", timedelta(minutes=5)),
    "1M": ("1d", "1mo", timedelta(minutes=15)),
    # 13 months lets us return the leading close needed for one-year returns.
    "1Y": ("1d", "13mo", timedelta(minutes=15)),
}
FUNDAMENTALS_TTL = timedelta(days=1)
FAILURE_TTL = timedelta(minutes=5)
SNAPSHOT = Path(__file__).with_name("data") / "sp500_snapshot_2026-09-15.json"


@dataclass(frozen=True)
class HistoryResult:
    frame: pd.DataFrame
    meta: dict[str, Any]


class DataService:
    """Expose normalized, cache-backed data without any web-framework dependency.

    ``mode='demo'`` never calls an external provider.  ``mode='research'`` is
    honest about provider failures: cached results are labelled stale and a
    complete miss is returned as an empty unavailable result.
    """

    def __init__(self, cache_dir: Path | None, mode: str, *, cache: MarketCache | None = None, freshness: FreshnessPolicy | None = None) -> None:
        if mode not in {"demo", "research", "production"}:
            raise ValueError("mode must be demo, research, or production")
        self.mode = mode
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        if cache is None and self.cache_dir is None:
            raise ValueError("A cache adapter or local cache directory is required")
        self.cache = cache if cache is not None else CacheStore(self.cache_dir)
        self.freshness = freshness or FreshnessPolicy()
        if self.cache.is_remote:
            baseline = json.loads(SNAPSHOT.read_text())
            _validate_snapshot(baseline)
            self._adopt_universe(baseline)
            saved = self._cache_value("universe:sp500")
            if saved:
                self._adopt_universe(saved[0])
        else:
            self._universe, self._universe_provenance = _load_snapshot(self.cache_dir)
        self.universe_as_of = self._universe_provenance["as_of"]
        self.universe_source = self._universe_provenance["source"]
        self._refresh_locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._failures: dict[str, tuple[float, str]] = {}
        self._last_universe_attempt = 0.0

    def search_universe(self, query: str = "", limit: int = 50) -> list[dict[str, Any]]:
        if self.mode != "demo":
            self.refresh_universe()
        if limit < 1:
            return []
        needle = query.strip().casefold()
        matches = [item for item in self._universe if not needle or needle in item["symbol"].casefold() or needle in item["name"].casefold()]
        return [dict(item) for item in matches[: min(limit, 600)]]

    def refresh_universe(self) -> bool:
        """Refresh the dated S&P 500 snapshot once per UTC day.

        A failed or malformed live table never replaces the last valid snapshot.
        The method is explicit so opening a local demo does not silently make a
        network request; a scheduled research worker can call it daily.
        """
        if self.mode == "demo":
            return False
        with self._lock_for("universe"):
            if time.monotonic() - self._last_universe_attempt < 86400:
                return False
            self._last_universe_attempt = time.monotonic()
            return self._refresh_remote_universe() if self.cache.is_remote else self._refresh_universe_now()

    def _refresh_universe_now(self) -> bool:
        snapshot_path = self.cache_dir / "universe_snapshot.json"
        if snapshot_path.exists():
            try:
                existing = json.loads(snapshot_path.read_text())
                refreshed = datetime.fromisoformat(existing["provenance"]["retrieved_at"].replace("Z", "+00:00"))
                if utc_now() - refreshed < timedelta(days=1):
                    return False
            except (OSError, KeyError, ValueError, json.JSONDecodeError):
                pass
        try:
            import httpx
            from io import StringIO
            response = httpx.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", timeout=12, follow_redirects=True)
            response.raise_for_status()
            tables = pd.read_html(StringIO(response.text))
            raw = tables[0].to_dict(orient="records")
            payload = _snapshot_payload(raw, "Wikipedia List of S&P 500 companies")
            _validate_snapshot(payload)
        except Exception:
            return False
        temporary = snapshot_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n")
        os.replace(temporary, snapshot_path)
        self._universe, self._universe_provenance = _load_snapshot(self.cache_dir)
        self.universe_as_of = self._universe_provenance["as_of"]
        self.universe_source = self._universe_provenance["source"]
        return True

    def universe_symbols(self) -> set[str]:
        return {item["symbol"] for item in self._universe}

    def instrument(self, symbol: str) -> dict[str, Any]:
        symbol = _normalize_symbol(symbol)
        market = MARKET_BY_SYMBOL.get(symbol)
        if market:
            return dict(market, sector=None)
        for item in self._universe:
            if item["symbol"] == symbol:
                return dict(item)
        # This is intentionally useful for research symbols but does not make it
        # eligible for an owner portfolio, which is validated against universe_symbols.
        return {"symbol": symbol, "name": symbol, "sector": "Unknown", "currency": None, "exchange": None, "timezone": "UTC"}

    def get_history(self, symbol: str, timeframe: str = "1Y") -> HistoryResult:
        symbol = _normalize_symbol(symbol)
        timeframe = timeframe.upper()
        if timeframe not in TIMEFRAMES:
            raise ValueError("timeframe must be one of 1D, 5D, 1M, 1Y")
        interval, period, _ = TIMEFRAMES[timeframe]
        ttl = self.freshness.history_ttl(timeframe)
        if self.mode == "demo":
            frame = _slice_demo(demo_history(symbol, interval), timeframe)
            return HistoryResult(frame, self._history_metadata(symbol, "demo", "demo", timeframe, interval, frame, ["Deterministic synthetic data; not market data."]))

        key = f"history:{symbol}:{timeframe}:{interval}"
        cached = self._cache_history(key)
        if cached and self.freshness.is_fresh(cached.refreshed_at, ttl):
            return HistoryResult(cached.frame, self._cached_history_metadata(symbol, cached.meta, timeframe, interval, cached.frame, "fresh"))
        lock = self._lock_for(key)
        with self._refresh_scope(key) as acquired:
            cached = self._cache_history(key)
            if cached and self.freshness.is_fresh(cached.refreshed_at, ttl):
                return HistoryResult(cached.frame, self._cached_history_metadata(symbol, cached.meta, timeframe, interval, cached.frame, "fresh"))
            if not acquired:
                if cached:
                    return HistoryResult(cached.frame, self._cached_history_metadata(symbol, cached.meta, timeframe, interval, cached.frame, "stale"))
                return HistoryResult(_empty_frame(), self._history_metadata(symbol, "yahoo_finance", "unavailable", timeframe, interval, _empty_frame(), ["Refresh pending or storage unavailable."]))
            failed = self._failures.get(key)
            if failed and time.monotonic() - failed[0] < FAILURE_TTL.total_seconds():
                if cached:
                    return HistoryResult(cached.frame, self._cached_history_metadata(symbol,cached.meta,timeframe,interval,cached.frame,"stale",list(cached.meta.get("notes",[]))+[failed[1]]))
                return HistoryResult(_empty_frame(),self._history_metadata(symbol,"yahoo_finance","unavailable",timeframe,interval,_empty_frame(),[failed[1]]))
            try:
                try:
                    frame = _window_history(self._yahoo_history(symbol, period, interval), timeframe)
                    actual_interval, status, notes = interval, "fresh", _close_basis_notes()
                except Exception as intraday_error:
                    if interval not in {"5m", "30m"}:
                        raise
                    frame = _window_history(self._yahoo_history(symbol, period, "1d"), timeframe)
                    actual_interval, status = "1d", "partial"
                    notes = _close_basis_notes() + [f"Intraday Yahoo data was unavailable ({type(intraday_error).__name__}); daily bars are shown."]
                meta = self._history_metadata(symbol, "yahoo_finance", status, timeframe, actual_interval, frame, notes)
                self.cache.put_history(key, frame, meta)
                self._failures.pop(key, None)
                return HistoryResult(frame, meta)
            except Exception as exc:
                self._failures[key] = (time.monotonic(),f"Provider unavailable: {type(exc).__name__}; retry after five minutes.")
                if cached:
                    notes = list(cached.meta.get("notes", [])) + [f"Live provider failed; serving stale cache: {type(exc).__name__}."]
                    return HistoryResult(cached.frame, self._cached_history_metadata(symbol, cached.meta, timeframe, interval, cached.frame, "stale", notes))
                return HistoryResult(_empty_frame(), self._history_metadata(symbol, "yahoo_finance", "unavailable", timeframe, interval, _empty_frame(), [f"Provider unavailable: {type(exc).__name__}."]))

    def get_fundamentals(self, symbol: str) -> dict[str, Any]:
        symbol = _normalize_symbol(symbol)
        if self.mode == "demo":
            data = demo_fundamentals(symbol)
            data["meta"] = _fundamental_meta("demo", "demo", ["Deterministic synthetic fundamentals; not issuer disclosures."], self.instrument(symbol).get("currency"),DEMO_AS_OF.isoformat())
            return data
        key = f"fundamentals:{symbol}"
        cached = self._cache_value(key)
        if cached and self.freshness.value_is_fresh(cached[0], cached[1], self.freshness.fundamentals_ttl):
            return _cached_value(cached[0], "fresh")
        with self._refresh_scope(key) as acquired:
            cached = self._cache_value(key)
            if cached and self.freshness.value_is_fresh(cached[0], cached[1], self.freshness.fundamentals_ttl):
                return _cached_value(cached[0], "fresh")
            if not acquired:
                return (_cached_value(cached[0], "stale") if cached else
                        _unavailable_fundamentals(symbol, "Refresh pending or storage unavailable.", self.instrument(symbol).get("currency")))
            try:
                result = self._yahoo_fundamentals(symbol)
                status = result.pop("_status", "fresh")
                result["meta"] = _fundamental_meta("yahoo_finance", status, result.pop("_notes", []), self.instrument(symbol).get("currency"),result.pop("_as_of",None))
                self.cache.put_value(key, result)
                return result
            except Exception as exc:
                if cached:
                    result = _cached_value(cached[0], "stale", f"Live provider failed; serving stale cache: {type(exc).__name__}.")
                    return result
                result = _unavailable_fundamentals(symbol, f"Provider unavailable: {type(exc).__name__}.", self.instrument(symbol).get("currency"))
                self._cache_failure(key, result)
                return result

    def risk_free_rate(self) -> dict[str, Any]:
        """Return FRED DGS10 as an annual decimal rate, never as a percent number."""
        if self.mode == "demo":
            return {"rate": 0.0425, "date": DEMO_AS_OF.date().isoformat(), "meta": _rate_meta("demo", "demo", ["Deterministic demo assumption."])}
        key = "fred:DGS10"
        cached = self._cache_value(key)
        if cached and self.freshness.value_is_fresh(cached[0], cached[1], self.freshness.risk_free_rate_ttl):
            return _cached_value(cached[0], "fresh")
        with self._refresh_scope(key) as acquired:
            cached = self._cache_value(key)
            if cached and self.freshness.value_is_fresh(cached[0], cached[1], self.freshness.risk_free_rate_ttl):
                return _cached_value(cached[0], "fresh")
            if not acquired:
                return (_cached_value(cached[0], "stale") if cached else
                        {"rate": None, "date": None, "meta": _rate_meta("fred", "unavailable", ["Refresh pending or storage unavailable."])})
            try:
                answer = _fetch_dgs10()
                answer["meta"] = _rate_meta("fred", "fresh", answer.pop("_notes", []))
                answer["meta"]["as_of"] = answer.get("date")
                self.cache.put_value(key, answer)
                return answer
            except Exception as exc:
                if cached:
                    return _cached_value(cached[0], "stale", f"FRED unavailable; serving stale cache: {type(exc).__name__}.")
                answer = {"rate": None, "date": None, "meta": _rate_meta("fred", "unavailable", [f"FRED unavailable: {type(exc).__name__}."])}
                self._cache_failure(key, answer)
                return answer

    def _cache_history(self, key):
        try:
            return self.cache.get_history(key)
        except Exception:
            return None

    def _cache_value(self, key):
        try:
            return self.cache.get_value(key)
        except Exception:
            return None

    def _cache_failure(self, key, payload):
        try:
            self.cache.put_value(key, payload)
        except Exception:
            pass  # Availability stays explicit; never fall back to a local store.

    @contextmanager
    def _refresh_scope(self, key):
        with self._lock_for(key):
            lease = self.cache.refresh_lease(key)
            try:
                acquired = lease.__enter__()
            except Exception:
                yield False
                return
            try:
                yield acquired
            finally:
                lease.__exit__(None, None, None)

    def _adopt_universe(self, payload):
        try:
            _validate_snapshot(payload)
        except (KeyError, ValueError, TypeError):
            return False
        self._universe = [dict(item, symbol=_normalize_symbol(item["symbol"]),
                               sector=canonical_sector(item.get("gics_sector") or item.get("sector")))
                          for item in payload["items"]]
        self._universe_provenance = payload["provenance"]
        self.universe_as_of = self._universe_provenance["as_of"]
        self.universe_source = self._universe_provenance["source"]
        return True

    def _refresh_remote_universe(self):
        import httpx
        from io import StringIO
        key = "universe:sp500"
        with self._refresh_scope(key) as acquired:
            cached = self._cache_value(key)
            if cached:
                self._adopt_universe(cached[0])
                if self.freshness.is_fresh(cached[1], self.freshness.universe_ttl):
                    return False
            if not acquired:
                return False
            try:
                response = httpx.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", timeout=12, follow_redirects=True)
                response.raise_for_status()
                raw = pd.read_html(StringIO(response.text))[0].to_dict(orient="records")
                payload = _snapshot_payload(raw, "Wikipedia List of S&P 500 companies")
                _validate_snapshot(payload)
                self.cache.put_value(key, payload)
                return self._adopt_universe(payload)
            except Exception:
                return False

    def _lock_for(self, key: str) -> threading.Lock:
        with self._locks_guard:
            return self._refresh_locks.setdefault(key, threading.Lock())

    def _history_metadata(self, symbol: str, source: str, status: str, timeframe: str, interval: str, frame: pd.DataFrame, notes: list[str]) -> dict[str, Any]:
        meta = _history_meta(source, status, timeframe, interval, frame, notes)
        meta["currency"] = self.instrument(symbol).get("currency")
        return meta

    def _cached_history_metadata(self, symbol: str, cached_meta: dict[str, Any], timeframe: str, interval: str, frame: pd.DataFrame, status: str, notes: list[str] | None = None) -> dict[str, Any]:
        meta = _cached_meta(cached_meta, timeframe, interval, frame, status, notes)
        meta["currency"] = self.instrument(symbol).get("currency")
        return meta

    @staticmethod
    def _yahoo_history(symbol: str, period: str, interval: str) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError as exc:  # clear unavailable result rather than import-time crash
            raise RuntimeError("yfinance is not installed") from exc
        ticker = yf.Ticker(symbol)
        args = {"interval":interval,"auto_adjust":False,"actions":False,"raise_errors":True,"timeout":15}
        if period == "13mo":
            args["start"] = (pd.Timestamp.now(tz="UTC") - pd.DateOffset(months=13)).date().isoformat()
        else:
            args["period"] = period
        raw = ticker.history(**args)
        return _normalize_ohlcv(raw)

    @staticmethod
    def _yahoo_fundamentals(symbol: str) -> dict[str, Any]:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("yfinance is not installed") from exc
        ticker = yf.Ticker(symbol)
        optional_notes=[]
        def section(name, default=None):
            try:
                return getattr(ticker,name)
            except Exception as exc:
                optional_notes.append(f"{name.replace('_',' ')} unavailable ({type(exc).__name__}).")
                return default
        info = section("info",{}) or {}
        income = section("quarterly_income_stmt")
        balance_sheet = section("quarterly_balance_sheet")
        cashflow = section("quarterly_cashflow")
        quarters, notes = normalize_quarters(income)
        price = number(info.get("regularMarketPrice") or info.get("currentPrice"))
        metrics = {
            "price": price, "market_cap": number(info.get("marketCap")), "pe": number(info.get("trailingPE")),
            "pb": number(info.get("priceToBook")), "eps": number(info.get("trailingEps")),
            "beta": number(info.get("beta")), "sharpe_6m": None, "capm_target": None,
        }
        estimate = _estimate_from_tables(section("earnings_estimate"), section("revenue_estimate"))
        consensus = _consensus_from_summary(section("recommendations_summary"), info)
        notes.extend(optional_notes)
        if len(quarters) < 8:
            notes.append(f"Only {len(quarters)} quarterly income statements were supplied; eight quarters were requested.")
        if estimate is None:
            notes.append("Next-quarter earnings and revenue estimates were unavailable from provider.")
        last = quarters[-1] if quarters else None
        return {
            "symbol": symbol, "metrics": metrics, "quarters": quarters, "estimate": estimate,
            "statements": _statements(last, info, balance_sheet, cashflow), "consensus": consensus,
            "income_flow": income_flow(last), "_notes": notes,
            "_status": "unavailable" if not info and not quarters else ("partial" if len(quarters) < 8 or estimate is None or optional_notes else "fresh"),
            "_as_of": last["period"] if last else None,
        }


def _load_snapshot(cache_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Use a validated last-known-good daily snapshot, otherwise the bundled one."""
    payload = json.loads(SNAPSHOT.read_text())
    saved = cache_dir / "universe_snapshot.json"
    if saved.exists():
        try:
            candidate = json.loads(saved.read_text())
            _validate_snapshot(candidate)
            payload = candidate
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            pass
    items = []
    for raw in payload["items"]:
        item = dict(raw)
        item["symbol"] = _normalize_symbol(item["symbol"])
        item["sector"] = canonical_sector(item.pop("gics_sector", None))
        items.append(item)
    return items, payload["provenance"]


def _snapshot_payload(rows: list[dict[str, Any]], source: str) -> dict[str, Any]:
    items = []
    for row in rows:
        symbol = _normalize_symbol(str(row.get("Symbol", "")))
        if symbol:
            items.append({"symbol": symbol, "name": str(row.get("Security", symbol)), "gics_sector": str(row.get("GICS Sector", "")), "currency": "USD", "exchange": "NYSE/Nasdaq", "timezone": "America/New_York"})
    return {"provenance": {"source": source, "url": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "retrieved_at": iso_now(), "as_of": utc_now().date().isoformat(), "count": len(items), "notes": ["Daily refreshed snapshot; the previous valid snapshot is retained if refresh validation fails."]}, "items": items}


def _validate_snapshot(payload: dict[str, Any]) -> None:
    items = payload.get("items")
    provenance = payload.get("provenance")
    if not isinstance(items, list) or not isinstance(provenance, dict):
        raise ValueError("Invalid universe snapshot structure")
    symbols = [str(item.get("symbol", "")).strip() for item in items]
    if not 500 <= len(items) <= 550 or len(set(symbols)) != len(items) or any(not symbol for symbol in symbols):
        raise ValueError("Universe snapshot is incomplete")


def _normalize_symbol(value: str) -> str:
    return value.strip().upper().replace(".", "-") if value.strip().upper() not in {"^SET.BK"} else "^SET.BK"


def _slice_demo(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    if timeframe == "1D": return frame.tail(78)
    if timeframe == "5D": return frame.tail(65)
    if timeframe == "1M": return frame.tail(22)
    return _window_history(frame,"1Y")


def _window_history(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Keep one prior daily close for annual return calculations."""
    if timeframe == "1Y" and not frame.empty:
        start=frame.index.max()-pd.DateOffset(years=1)
        return pd.concat([frame.loc[frame.index < start].tail(1),frame.loc[frame.index >= start]])
    return frame


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["open", "high", "low", "close", "volume"], index=pd.DatetimeIndex([], tz="UTC"))


def _normalize_ohlcv(raw: pd.DataFrame) -> pd.DataFrame:
    if raw is None or raw.empty:
        raise ValueError("Yahoo returned no OHLCV bars")
    frame = raw.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    frame.columns = [str(col).strip().casefold().replace(" ", "_") for col in frame.columns]
    required = ["open", "high", "low", "close", "volume"]
    missing = [column for column in required[:-1] if column not in frame.columns]
    if missing:
        raise ValueError(f"Yahoo bars missing columns: {', '.join(missing)}")
    if "volume" not in frame:
        frame["volume"] = float("nan")
    frame = frame[required].apply(pd.to_numeric, errors="coerce")
    frame.index = pd.to_datetime(frame.index, utc=True)
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    frame=frame.loc[~frame.index.isna()]
    ohlc=["open","high","low","close"]
    invalid_range = (frame["high"] < frame[["open", "close", "low"]].max(axis=1)) | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
    invalid = invalid_range | ~np.isfinite(frame[ohlc]).all(axis=1) | (frame[ohlc] <= 0).any(axis=1)
    frame.loc[invalid,ohlc]=np.nan
    frame.loc[~np.isfinite(frame["volume"]) | (frame["volume"]<0),"volume"]=np.nan
    if frame.empty or frame["close"].notna().sum() == 0:
        raise ValueError("No valid OHLCV bars after validation")
    return frame


def _history_meta(source: str, status: str, timeframe: str, interval: str, frame: pd.DataFrame, notes: list[str]) -> dict[str, Any]:
    start = frame.index.min().isoformat().replace("+00:00", "Z") if not frame.empty else None
    end = frame.index.max().isoformat().replace("+00:00", "Z") if not frame.empty else None
    return {"source": source, "as_of": end, "retrieved_at": iso_now(), "status": status, "requested_window": timeframe, "actual_start": start, "actual_end": end, "currency": None, "interval": interval, "sample_count": len(frame), "notes": notes}


def _cached_meta(meta: dict[str, Any], timeframe: str, interval: str, frame: pd.DataFrame, status: str, notes: list[str] | None = None) -> dict[str, Any]:
    cached = dict(meta)
    cached["status"] = cached["status"] if status == "fresh" and cached.get("status") in {"partial", "stale"} else status
    cached["requested_window"] = timeframe
    cached["interval"] = cached.get("interval", interval)
    cached["sample_count"] = len(frame)
    cached["actual_start"] = frame.index.min().isoformat().replace("+00:00", "Z") if not frame.empty else None
    cached["actual_end"] = frame.index.max().isoformat().replace("+00:00", "Z") if not frame.empty else None
    cached["as_of"] = cached.get("as_of") or cached["actual_end"]
    cached["notes"] = notes if notes is not None else list(cached.get("notes", []))
    return cached


def _close_basis_notes() -> list[str]:
    return ["Yahoo history is requested with auto_adjust=False. Close is split-adjusted by Yahoo but excludes dividend adjustment; use it consistently for V1 price and return calculations."]


def _fundamental_meta(source: str, status: str, notes: list[str], currency: str | None = None, as_of: str | None = None) -> dict[str, Any]:
    return {"source": source, "as_of": as_of, "retrieved_at": iso_now(), "status": status, "requested_window": None, "actual_start": None, "actual_end": None, "currency": currency, "interval": None, "sample_count": None, "notes": notes}


def _rate_meta(source: str, status: str, notes: list[str]) -> dict[str, Any]:
    return {"source": source, "as_of": None, "retrieved_at": iso_now(), "status": status, "requested_window": None, "actual_start": None, "actual_end": None, "currency": "USD", "interval": "daily", "sample_count": None, "notes": notes}


def _unavailable_fundamentals(symbol: str, note: str, currency: str | None = None) -> dict[str, Any]:
    return {"symbol": symbol, "metrics": {key: None for key in ("price", "market_cap", "pe", "pb", "eps", "beta", "sharpe_6m", "capm_target")}, "quarters": [], "estimate": None, "statements": {"valuation": [], "income": [], "balance_cashflow": []}, "consensus": {"buy": None, "hold": None, "sell": None, "target_low": None, "target_mean": None, "target_high": None, "analyst_count": None}, "income_flow": income_flow(None), "meta": _fundamental_meta("yahoo_finance", "unavailable", [note], currency)}


def _within_value_ttl(cached: tuple[dict[str, Any], datetime], normal_ttl: timedelta) -> bool:
    value, refreshed_at = cached
    status = value.get("meta", {}).get("status")
    return utc_now() - refreshed_at <= (FAILURE_TTL if status == "unavailable" else normal_ttl)


def _cached_value(value: dict[str, Any], status: str, extra_note: str | None = None) -> dict[str, Any]:
    result = dict(value)
    meta = dict(result.get("meta", {}))
    # Do not reinterpret an unavailable cached failure as fresh data.
    previous=meta.get("status")
    meta["status"] = previous if previous == "unavailable" or (previous in {"partial", "stale"} and status == "fresh") else status
    if extra_note:
        meta["notes"] = list(meta.get("notes", [])) + [extra_note]
    result["meta"] = meta
    return result


def _estimate_from_tables(earnings: pd.DataFrame | None, revenue: pd.DataFrame | None) -> dict[str, Any] | None:
    """Read the +1q next-quarter estimate; 0q is the current quarter."""
    earnings_row, earnings_period = _estimate_row(earnings)
    revenue_row, revenue_period = _estimate_row(revenue)
    eps = number(earnings_row.get("avg")) if earnings_row is not None else None
    revenue_value = number(revenue_row.get("avg")) if revenue_row is not None else None
    if eps is None and revenue_value is None:
        return None
    return {"period": earnings_period or revenue_period or "next_quarter", "revenue": revenue_value, "eps": eps}


def _estimate_row(frame: pd.DataFrame | None) -> tuple[pd.Series | None, str | None]:
    if frame is None or frame.empty:
        return None, None
    normalized = frame.copy()
    normalized.columns = [str(column).casefold() for column in normalized.columns]
    if "+1q" in normalized.index:
        return normalized.loc["+1q"], "Next quarter (+1q)"
    return None, None


def _consensus_from_summary(summary: pd.DataFrame | None, info: dict[str, Any]) -> dict[str, float | None]:
    row: pd.Series | None = None
    if summary is not None and not summary.empty:
        normalized = summary.copy()
        normalized.columns = [str(column).casefold() for column in normalized.columns]
        if "period" in normalized.columns:
            current = normalized[normalized["period"].astype(str).eq("0m")]
            row = current.iloc[0] if not current.empty else normalized.iloc[0]
        else:
            row = normalized.loc["0m"] if "0m" in normalized.index else normalized.iloc[0]
    def value(name: str) -> float | None:
        return number(row.get(name.casefold())) if row is not None else None
    strong_buy, buy = value("strongBuy"), value("buy")
    hold = value("hold")
    sell, strong_sell = value("sell"), value("strongSell")
    return {
        "buy": _sum_counts(strong_buy, buy), "hold": hold, "sell": _sum_counts(sell, strong_sell),
        "target_low": number(info.get("targetLowPrice")), "target_mean": number(info.get("targetMeanPrice")),
        "target_high": number(info.get("targetHighPrice")), "analyst_count": number(info.get("numberOfAnalystOpinions")),
    }


def _sum_counts(first: float | None, second: float | None) -> float | None:
    return None if first is None and second is None else (first or 0) + (second or 0)


def _statements(last: dict[str, Any] | None, info: dict[str, Any], balance_sheet: pd.DataFrame | None, cashflow: pd.DataFrame | None) -> dict[str, list[dict[str, Any]]]:
    quarter = last or {}
    return {
        "valuation": [{"label": "Market Capitalization", "value": number(info.get("marketCap")), "unit": "currency"}, {"label": "Price / Earnings", "value": number(info.get("trailingPE")), "unit": "ratio"}, {"label": "Price / Book", "value": number(info.get("priceToBook")), "unit": "ratio"}],
        "income": [{"label": "Revenue", "value": quarter.get("revenue"), "unit": "currency"}, {"label": "Gross Profit", "value": quarter.get("gross_profit"), "unit": "currency"}, {"label": "Operating Income", "value": quarter.get("operating_income"), "unit": "currency"}, {"label": "Net Income", "value": quarter.get("net_income"), "unit": "currency"}],
        "balance_cashflow": [{"label": "Cash", "value": _statement_value(balance_sheet, ("Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents", "Cash Financial")), "unit": "currency"}, {"label": "Debt", "value": _statement_value(balance_sheet, ("Total Debt", "Long Term Debt And Capital Lease Obligation", "Long Term Debt")), "unit": "currency"}, {"label": "Free Cash Flow", "value": _statement_value(cashflow, ("Free Cash Flow",)), "unit": "currency"}],
    }


def _statement_value(statement: pd.DataFrame | None, labels: tuple[str, ...]) -> float | None:
    if statement is None or statement.empty:
        return None
    for label in labels:
        if label in statement.index:
            row = statement.loc[label]
            for value in row.sort_index(ascending=False):
                parsed = number(value)
                if parsed is not None:
                    return parsed
    return None


def _fetch_dgs10() -> dict[str, Any]:
    # FRED's documented CSV endpoint requires no API key.  If a caller supplies
    # FRED_API_KEY, use the JSON endpoint instead to support tighter rate limits.
    api_key = os.getenv("FRED_API_KEY")
    if api_key:
        url = "https://api.stlouisfed.org/fred/series/observations?" + urlencode({"series_id": "DGS10", "api_key": api_key, "file_type": "json", "sort_order": "desc", "limit": 10})
        with urlopen(url, timeout=15) as response:  # nosec B310 - documented public provider URL
            observations = json.loads(response.read())["observations"]
        for observation in observations:
            value = number(observation.get("value"))
            if value is not None:
                return {"rate": value / 100, "date": observation["date"], "_notes": ["DGS10 annual yield converted from percent to fraction."]}
    else:
        with urlopen("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10", timeout=15) as response:  # nosec B310 - documented public provider URL
            csv = response.read().decode("utf-8")
        for line in reversed(csv.splitlines()[1:]):
            date, _, raw = line.partition(",")
            value = number(raw)
            if value is not None:
                return {"rate": value / 100, "date": date, "_notes": ["DGS10 annual yield converted from percent to fraction via FRED public CSV."]}
    raise ValueError("FRED returned no DGS10 observation")
