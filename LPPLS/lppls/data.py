"""Market-data providers and normalization."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

import pandas as pd

from .config import InstrumentConfig


class PriceProvider(Protocol):
    def history(self, symbol: str) -> pd.Series:
        ...


class DataDownloadError(RuntimeError):
    pass


def normalize_close(frame: pd.DataFrame, symbol: str) -> pd.Series:
    """Extract a clean adjusted-close series from common yfinance layouts."""

    if frame is None or frame.empty:
        raise DataDownloadError(f"No data returned for {symbol}")

    close: pd.Series | pd.DataFrame
    if isinstance(frame.columns, pd.MultiIndex):
        if "Close" in frame.columns.get_level_values(0):
            close = frame.xs("Close", axis=1, level=0)
        elif "Close" in frame.columns.get_level_values(-1):
            close = frame.xs("Close", axis=1, level=-1)
        else:
            raise DataDownloadError(f"Close column missing for {symbol}")
        if isinstance(close, pd.DataFrame):
            if symbol in close.columns:
                close = close[symbol]
            else:
                close = close.iloc[:, 0]
    else:
        if "Close" not in frame.columns:
            raise DataDownloadError(f"Close column missing for {symbol}")
        close = frame["Close"]

    series = pd.to_numeric(close, errors="coerce").dropna()
    series = series[series > 0]
    if series.empty:
        raise DataDownloadError(f"No positive closing prices for {symbol}")

    index = pd.to_datetime(series.index, errors="coerce", utc=True)
    valid = ~index.isna()
    series = pd.Series(series.to_numpy()[valid], index=index[valid], name="close")
    series.index = series.index.tz_convert(None)
    series = series[~series.index.duplicated(keep="last")].sort_index()
    return series.astype(float)


class YahooFinanceProvider:
    """Weekly adjusted data from the first available record through now."""

    def history(self, symbol: str) -> pd.Series:
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise DataDownloadError(
                "yfinance is required; install dependencies from requirements.txt"
            ) from exc

        try:
            frame = yf.download(
                symbol,
                period="max",
                interval="1wk",
                auto_adjust=True,
                progress=False,
                threads=False,
            )
        except Exception as exc:  # yfinance raises several transport exception types
            raise DataDownloadError(f"Could not download {symbol}: {exc}") from exc
        return normalize_close(frame, symbol)


def download_unique(
    instruments: Iterable[InstrumentConfig], provider: PriceProvider
) -> tuple[dict[str, pd.Series], dict[str, str]]:
    """Download every unique symbol once and return data plus per-symbol errors."""

    data: dict[str, pd.Series] = {}
    errors: dict[str, str] = {}
    for instrument in instruments:
        if instrument.symbol in data or instrument.symbol in errors:
            continue
        try:
            data[instrument.symbol] = provider.history(instrument.symbol)
        except DataDownloadError as exc:
            errors[instrument.symbol] = str(exc)
    return data, errors
