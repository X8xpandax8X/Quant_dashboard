from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pandas as pd
import pytest

from data_engine.cache import CacheStore
from data_engine.fundamentals import income_flow, normalize_quarters
from data_engine.instruments import MARKETS, canonical_sector
from data_engine.service import DataService, _normalize_ohlcv


def test_demo_is_deterministic_and_rich(tmp_path: Path) -> None:
    first = DataService(tmp_path / "one", "demo")
    second = DataService(tmp_path / "two", "demo")
    a = first.get_history("AAPL", "1Y")
    b = second.get_history("AAPL", "1Y")
    pd.testing.assert_frame_equal(a.frame, b.frame)
    assert a.meta["status"] == "demo"
    fundamentals = first.get_fundamentals("any-private-symbol")
    assert len(fundamentals["quarters"]) == 8
    assert fundamentals["estimate"] is not None
    assert fundamentals["meta"]["status"] == "demo"


def test_universe_snapshot_and_sector_aliases(tmp_path: Path) -> None:
    service = DataService(tmp_path, "demo")
    assert len(service.universe_symbols()) == 503
    assert "AAPL" in service.universe_symbols()
    assert service.instrument("BRK.B")["sector"] == "Financials"
    assert canonical_sector("Consumer Defensive") == "Consumer Staples"
    assert canonical_sector("not a sector") == "Unknown"
    assert {item["symbol"] for item in MARKETS} == {"^GSPC", "^NDX", "^VIX", "^N225", "^KS200", "^SET.BK", "BTC-USD"}


def test_atomic_parquet_cache_round_trip(tmp_path: Path) -> None:
    store = CacheStore(tmp_path)
    index = pd.date_range("2025-01-01", periods=2, tz="UTC")
    frame = pd.DataFrame({"open": [1, 2], "high": [2, 3], "low": [0.5, 1.5], "close": [1.5, 2.5], "volume": [None, 7]}, index=index)
    store.put_history("AAPL:1Y", frame, {"source": "test", "notes": []})
    cached = store.get_history("AAPL:1Y")
    assert cached is not None
    pd.testing.assert_frame_equal(cached.frame, frame, check_freq=False)
    assert list((tmp_path / "history").glob("*.tmp")) == []


def test_per_key_refresh_is_deduplicated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = DataService(tmp_path, "research")
    calls = 0
    gate = threading.Lock()
    frame = DataService(tmp_path / "demo", "demo").get_history("AAPL").frame

    def fetch(*_args: object) -> pd.DataFrame:
        nonlocal calls
        with gate:
            calls += 1
        return frame

    monkeypatch.setattr(service, "_yahoo_history", fetch)
    threads = [threading.Thread(target=lambda: service.get_history("AAPL", "1Y")) for _ in range(8)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert calls == 1


def test_stale_cache_is_returned_on_provider_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = DataService(tmp_path, "research")
    frame = DataService(tmp_path / "demo", "demo").get_history("AAPL").frame
    key = "history:AAPL:1Y:1d"
    service.cache.put_history(key, frame, {"source": "yahoo_finance", "notes": ["cached"]})
    with sqlite3.connect(tmp_path / "index.sqlite3") as conn:
        conn.execute("UPDATE history_cache SET refreshed_at='2000-01-01T00:00:00Z' WHERE cache_key=?", (key,))
    monkeypatch.setattr(service, "_yahoo_history", lambda *_args: (_ for _ in ()).throw(RuntimeError("offline")))
    result = service.get_history("AAPL")
    assert result.meta["status"] == "stale"
    assert len(result.frame) == len(frame)


def test_provider_failure_without_cache_is_honestly_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = DataService(tmp_path, "research")
    monkeypatch.setattr(service, "_yahoo_history", lambda *_args: (_ for _ in ()).throw(RuntimeError("offline")))
    result = service.get_history("AAPL")
    assert result.meta["status"] == "unavailable"
    assert result.frame.empty


def test_ohlcv_normalization_preserves_missing_volume() -> None:
    raw = pd.DataFrame({"Open": [1], "High": [2], "Low": [0.5], "Close": [1.5]}, index=pd.DatetimeIndex(["2025-01-01"]))
    result = _normalize_ohlcv(raw)
    assert result.index.tz is not None
    assert pd.isna(result.loc[result.index[0], "volume"])


def test_fundamentals_missingness_negative_growth_and_waterfall() -> None:
    columns = pd.date_range("2024-03-31", periods=6, freq="QE")
    income = pd.DataFrame({
        columns[0]: [100, 60, 20, 10, 40, 2], columns[1]: [120, 70, 25, 10, 50, 2.5],
        columns[2]: [130, 75, 30, 12, 55, 3], columns[3]: [140, 80, 35, 12, 60, 3.2],
        columns[4]: [-10, None, -2, -4, None, -0.2], columns[5]: [20, 10, 2, 1, 10, 0.1],
    }, index=["Total Revenue", "Gross Profit", "Operating Income", "Net Income", "Cost Of Revenue", "Diluted EPS"])
    rows, notes = normalize_quarters(income)
    assert rows[-1]["revenue_qoq"] is None
    assert any("zero or negative" in note for note in notes)
    flow = income_flow(rows[-1])
    assert flow["kind"] == "waterfall"
    assert rows[-1]["taxes"] is None
