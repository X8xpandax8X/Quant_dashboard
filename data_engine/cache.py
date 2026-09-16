"""Small SQLite index plus atomic Parquet history storage."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class CachedHistory:
    frame: pd.DataFrame
    meta: dict[str, Any]
    refreshed_at: datetime


class CacheStore:
    """Cache metadata in SQLite; payloads live as independently replaceable files."""

    def __init__(self, cache_dir: Path) -> None:
        self.is_remote = False
        self.cache_dir = Path(cache_dir)
        self.history_dir = self.cache_dir / "history"
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.cache_dir / "index.sqlite3"
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS history_cache (
                cache_key TEXT PRIMARY KEY, path TEXT NOT NULL, refreshed_at TEXT NOT NULL,
                meta_json TEXT NOT NULL)"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS value_cache (
                cache_key TEXT PRIMARY KEY, refreshed_at TEXT NOT NULL, value_json TEXT NOT NULL)"""
            )

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _safe_key(key: str) -> str:
        return "".join(char if char.isalnum() or char in "-_." else "_" for char in key)

    def get_history(self, key: str) -> CachedHistory | None:
        with self._connect() as conn:
            # Coordinate file reads with version retirement across processes.
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT path, refreshed_at, meta_json FROM history_cache WHERE cache_key=?", (key,)
            ).fetchone()
            if not row:
                return None
            path = self.cache_dir / row[0]
            try:
                frame = pd.read_parquet(path)
                frame.index = pd.to_datetime(frame.index, utc=True)
                return CachedHistory(frame, json.loads(row[2]), datetime.fromisoformat(row[1].replace("Z", "+00:00")))
            except (OSError, ValueError):
                return None

    def put_history(self, key: str, frame: pd.DataFrame, meta: dict[str, Any]) -> None:
        """Write a complete parquet file before making it visible in the SQLite index."""
        # Immutable versions keep a reader's payload and metadata in agreement
        # across the transaction that advances the index to a newer version.
        filename = f"{self._safe_key(key)}-{uuid4().hex}.parquet"
        relative = Path("history") / filename
        path = self.cache_dir / relative
        temporary = path.with_suffix(".parquet.tmp")
        # pandas/pyarrow refuses arbitrary extensions in some configurations; the
        # explicit parquet engine keeps the cache format unambiguous.
        frame.to_parquet(temporary, engine="pyarrow", index=True)
        os.replace(temporary, path)
        refreshed = iso_now()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            old = conn.execute("SELECT path FROM history_cache WHERE cache_key=?", (key,)).fetchone()
            conn.execute(
                "INSERT INTO history_cache(cache_key,path,refreshed_at,meta_json) VALUES(?,?,?,?) "
                "ON CONFLICT(cache_key) DO UPDATE SET path=excluded.path, refreshed_at=excluded.refreshed_at, meta_json=excluded.meta_json",
                (key, str(relative), refreshed, json.dumps(meta, default=str)),
            )
        if old:
            (self.cache_dir / old[0]).unlink(missing_ok=True)

    def get_value(self, key: str) -> tuple[dict[str, Any], datetime] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value_json, refreshed_at FROM value_cache WHERE cache_key=?", (key,)).fetchone()
        if not row:
            return None
        try:
            value = json.loads(row[0])
            refreshed_at = datetime.fromisoformat(row[1].replace("Z", "+00:00"))
            if not isinstance(value, dict) or refreshed_at.tzinfo is None:
                return None
            return value, refreshed_at
        except (TypeError, ValueError):
            # A malformed cache entry is disposable. Callers treat this as a miss
            # and either replace it from the provider or cache an unavailable result.
            return None

    def put_value(self, key: str, value: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO value_cache(cache_key,refreshed_at,value_json) VALUES(?,?,?) "
                "ON CONFLICT(cache_key) DO UPDATE SET refreshed_at=excluded.refreshed_at, value_json=excluded.value_json",
                (key, iso_now(), json.dumps(value, default=str)),
            )

    @contextmanager
    def refresh_lease(self, key: str):
        """Local cache has no cross-process lease; the service lock is sufficient."""
        del key
        yield True
