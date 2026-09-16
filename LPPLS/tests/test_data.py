from __future__ import annotations

import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from lppls.config import InstrumentConfig
from lppls.data import (
    DataDownloadError,
    YahooFinanceProvider,
    download_unique,
    normalize_close,
)


def test_normalize_close_sorts_filters_and_deduplicates() -> None:
    frame = pd.DataFrame(
        {"Close": ["12", "bad", 10, 11, 0, -2]},
        index=pd.to_datetime(
            [
                "2024-01-14",
                "2024-01-21",
                "2024-01-07",
                "2024-01-07",
                "2024-01-28",
                "2024-02-04",
            ],
            utc=True,
        ),
    )

    result = normalize_close(frame, "TEST")

    assert result.name == "close"
    assert result.index.tz is None
    assert result.index.tolist() == [
        pd.Timestamp("2024-01-07"),
        pd.Timestamp("2024-01-14"),
    ]
    assert result.tolist() == [11.0, 12.0]


def test_normalize_close_handles_yfinance_multiindex() -> None:
    columns = pd.MultiIndex.from_tuples([("Close", "ABC"), ("Open", "ABC")])
    frame = pd.DataFrame(
        [[5.0, 4.5], [6.0, 5.5]],
        index=pd.date_range("2024-01-01", periods=2, freq="W"),
        columns=columns,
    )

    result = normalize_close(frame, "ABC")

    assert result.tolist() == [5.0, 6.0]


@pytest.mark.parametrize(
    "frame",
    [pd.DataFrame(), pd.DataFrame({"Open": [1.0]}), pd.DataFrame({"Close": [0, -1]})],
)
def test_normalize_close_rejects_unusable_frames(frame: pd.DataFrame) -> None:
    with pytest.raises(DataDownloadError):
        normalize_close(frame, "ABC")


def test_download_unique_calls_provider_once_per_symbol_and_collects_errors() -> None:
    instruments = (
        InstrumentConfig("AAA", "First", "#111111"),
        InstrumentConfig("AAA", "Duplicate", "#222222"),
        InstrumentConfig("BAD", "Unavailable", "#333333"),
    )

    class Provider:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def history(self, symbol: str) -> pd.Series:
            self.calls.append(symbol)
            if symbol == "BAD":
                raise DataDownloadError("offline fixture failure")
            return pd.Series([1.0], index=[pd.Timestamp("2024-01-07")], name="close")

    provider = Provider()
    data, errors = download_unique(instruments, provider)

    assert provider.calls == ["AAA", "BAD"]
    assert list(data) == ["AAA"]
    assert errors == {"BAD": "offline fixture failure"}


def test_yahoo_provider_requests_complete_weekly_history_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_download(symbol: str, **kwargs: object) -> pd.DataFrame:
        captured["symbol"] = symbol
        captured.update(kwargs)
        return pd.DataFrame(
            {"Close": [10.0, 11.0]},
            index=pd.date_range("2001-01-07", periods=2, freq="W"),
        )

    monkeypatch.setitem(
        sys.modules, "yfinance", SimpleNamespace(download=fake_download)
    )

    result = YahooFinanceProvider().history("ABC")

    assert result.tolist() == [10.0, 11.0]
    assert captured == {
        "symbol": "ABC",
        "period": "max",
        "interval": "1wk",
        "auto_adjust": True,
        "progress": False,
        "threads": False,
    }
