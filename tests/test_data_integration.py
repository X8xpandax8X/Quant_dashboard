from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
import sys

import numpy as np
import pandas as pd

from data_engine.fundamentals import income_flow, number
from data_engine.service import DataService, _estimate_from_tables, _cached_value, _normalize_ohlcv, _window_history


def test_next_quarter_is_not_current_quarter():
    estimates=pd.DataFrame({"avg":[1,2,3]},index=["0q","+1q","0y"])
    result=_estimate_from_tables(estimates,estimates*100)
    assert result["eps"]==2 and result["revenue"]==200
    assert _estimate_from_tables(estimates.drop(index="+1q"),None) is None


def test_sankey_checks_operating_node_and_missing_waterfall():
    quarter=dict(revenue=100,gross_profit=60,operating_income=30,net_income=25,cogs=40,opex=30,taxes=5)
    assert income_flow(quarter)["kind"]=="sankey"
    quarter["net_income"]=15
    assert income_flow(quarter)["kind"]=="waterfall"
    quarter["gross_profit"]=None
    assert income_flow(quarter)["kind"]=="waterfall"
    assert number(np.inf) is None


def test_bad_ohlcv_preserves_gap_without_fabricated_volume():
    frame=pd.DataFrame({"Open":[10,0,12],"High":[11,0,13],"Low":[9,0,11],"Close":[10,0,12],"Volume":[10,-1,np.inf]},index=pd.date_range("2026-01-01",periods=3))
    clean=_normalize_ohlcv(frame)
    assert len(clean)==3 and np.isnan(clean.iloc[1]["close"])
    assert clean["close"].pct_change(fill_method=None).dropna().empty
    assert clean["volume"].isna().sum()==2


def test_daily_fallback_and_partial_cache(tmp_path,monkeypatch):
    service=DataService(tmp_path,"research")
    frame=DataService(tmp_path/"demo","demo").get_history("MSFT","1Y").frame.tail(5)
    calls=[]
    def provider(symbol,period,interval):
        calls.append(interval)
        if interval!="1d": raise RuntimeError("intraday missing")
        return frame
    monkeypatch.setattr(service,"_yahoo_history",provider)
    first=service.get_history("MSFT","5D")
    second=service.get_history("MSFT","5D")
    assert calls==["30m","1d"]
    assert first.meta["interval"]==second.meta["interval"]=="1d"
    assert first.meta["status"]==second.meta["status"]=="partial"
    assert first.meta["retrieved_at"]==second.meta["retrieved_at"]


def test_unavailable_history_not_retried_on_every_render(tmp_path,monkeypatch):
    service=DataService(tmp_path,"research")
    calls=[]
    def provider(*args):
        calls.append(args)
        raise RuntimeError("offline")
    monkeypatch.setattr(service,"_yahoo_history",provider)
    assert service.get_history("MSFT").meta["status"]=="unavailable"
    assert service.get_history("MSFT").meta["status"]=="unavailable"
    assert len(calls)==1


def test_value_cache_preserves_partial_and_observation_dates():
    value={"meta":{"status":"partial","as_of":"2026Q2","retrieved_at":"2026-09-01T00:00:00Z","notes":["Missing estimate"]}}
    cached=_cached_value(value,"fresh")
    assert cached==value
    stale=_cached_value(value,"stale","Offline")
    assert stale["meta"]["status"]=="stale" and value["meta"]["notes"]==["Missing estimate"]


def test_calendar_year_window_includes_one_baseline():
    index=pd.date_range("2024-01-01", "2026-09-14",tz="UTC")
    frame=pd.DataFrame({"close":range(len(index))},index=index)
    result=_window_history(frame,"1Y")
    assert result.index[0]==pd.Timestamp("2025-09-13",tz="UTC")
    assert result.index[-1]==index[-1]


def test_optional_estimate_failure_preserves_core_fundamentals(monkeypatch):
    class Ticker:
        info={"currentPrice":100,"marketCap":1000000}
        quarterly_income_stmt=pd.DataFrame({pd.Timestamp("2026-06-30"):[100,60,20,10]},index=["Total Revenue","Gross Profit","Operating Income","Net Income"])
        quarterly_balance_sheet=None
        quarterly_cashflow=None
        revenue_estimate=None
        recommendations_summary=None
        @property
        def earnings_estimate(self): raise RuntimeError("optional endpoint failed")
    monkeypatch.setitem(sys.modules,"yfinance",SimpleNamespace(Ticker=lambda _:Ticker()))
    result=DataService._yahoo_fundamentals("MSFT")
    assert result["metrics"]["price"]==100
    assert len(result["quarters"])==1 and result["estimate"] is None
    assert result["_status"]=="partial"


def test_demo_intraday_and_daily_quotes_agree(tmp_path):
    service=DataService(tmp_path,"demo")
    daily=service.get_history("MSFT","1Y").frame
    intraday=service.get_history("MSFT","1D").frame
    assert abs(daily["close"].iloc[-1]-intraday["close"].iloc[-1])<1e-8
    five=service.get_history("MSFT","5D").frame
    assert len(five)==65
    assert five.index.normalize().nunique()==5
def test_cache_concurrent_replacement_keeps_payload_metadata_together(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import pandas as pd
    from data_engine.cache import CacheStore

    cache = CacheStore(tmp_path)
    def write(version):
        frame = pd.DataFrame({"close": [float(version)]}, index=pd.date_range("2026-01-01", periods=1, tz="UTC"))
        cache.put_history("same-key", frame, {"version": version})
    write(0)
    def writer():
        for version in range(1, 20):
            write(version)
    def reader():
        for _ in range(30):
            item = cache.get_history("same-key")
            assert item is not None
            assert item.frame["close"].iloc[0] == item.meta["version"]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for result in [pool.submit(writer), pool.submit(reader), pool.submit(reader)]:
            result.result()
    assert len(list((tmp_path / "history").glob("*.parquet"))) == 1


def test_corrupt_value_cache_is_treated_as_a_miss(tmp_path):
    import sqlite3
    from data_engine.cache import CacheStore

    cache = CacheStore(tmp_path)
    with sqlite3.connect(tmp_path / "index.sqlite3") as connection:
        connection.execute(
            "INSERT INTO value_cache(cache_key, refreshed_at, value_json) VALUES(?, ?, ?)",
            ("fred:DGS10", "2026-01-01T00:00:00Z", "{broken"),
        )
    assert cache.get_value("fred:DGS10") is None

    with sqlite3.connect(tmp_path / "index.sqlite3") as connection:
        connection.execute(
            "UPDATE value_cache SET refreshed_at=?, value_json=? WHERE cache_key=?",
            ("not-a-timestamp", "[]", "fred:DGS10"),
        )
    assert cache.get_value("fred:DGS10") is None
