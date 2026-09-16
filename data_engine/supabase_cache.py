"""Private Supabase Storage/PostgREST adapter for shared market artifacts.

This adapter is intentionally server-only: callers supply a separately scoped
market-ingestion credential.  It has no facility for portfolio/user requests.
"""

from __future__ import annotations

import hashlib
import io
import json
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Iterator
from urllib.parse import quote, urlparse
from uuid import uuid4

import httpx
import pandas as pd

from .cache import CachedHistory, iso_now
from .instruments import canonical_sector


class RemoteCacheError(RuntimeError):
    """Sanitized remote-cache failure safe to expose in service metadata."""


class SupabaseMarketCache:
    """Versioned remote market cache backed by private Storage and metadata RPCs."""

    is_remote = True
    _REQUIRED_RECORD_FIELDS = {
        "format_version", "kind", "bucket", "object_key", "object_version",
        "checksum_sha256", "content_type", "source", "observed_at", "retrieved_at",
        "coverage_start", "coverage_end", "row_count", "quality_json",
    }

    def __init__(
        self, base_url: str, service_role_key: str, *, bucket: str = "market-data",
        prefix: str = "equities", transport: httpx.BaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        parsed = urlparse(base_url)
        local = parsed.hostname in {"localhost", "127.0.0.1"}
        if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ("", "/") or not (parsed.scheme == "https" or (local and parsed.scheme == "http"))):
            raise ValueError("base_url must be trusted HTTPS or a local test URL")
        if not service_role_key:
            raise ValueError("service_role_key is required for market ingestion")
        self.base_url = base_url.rstrip("/")
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        headers = {"apikey": service_role_key}
        if service_role_key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {service_role_key}"
        self._client = httpx.Client(transport=transport, timeout=timeout, headers=headers)
        self._leases: ContextVar[dict[str, dict[str, Any]]] = ContextVar("market_cache_leases", default={})

    def close(self) -> None:
        self._client.close()

    def get_history(self, key: str) -> CachedHistory | None:
        record = self._metadata(key)
        if not record or record.get("kind") != "history":
            return None
        payload = self._download_verified(record)
        if payload is None:
            return None
        try:
            frame = pd.read_parquet(io.BytesIO(payload))
            frame.index = pd.to_datetime(frame.index, utc=True)
            return CachedHistory(frame, dict(record["quality_json"]), _record_time(record))
        except (ValueError, OSError, TypeError):
            return None

    def put_history(self, key: str, frame: pd.DataFrame, meta: dict[str, Any]) -> None:
        buffer = io.BytesIO()
        frame.to_parquet(buffer, engine="pyarrow", index=True)
        self._publish(key, "history", buffer.getvalue(), "application/vnd.apache.parquet", meta,
                      coverage_start=meta.get("actual_start"), coverage_end=meta.get("actual_end"),
                      row_count=len(frame))

    def get_value(self, key: str) -> tuple[dict[str, Any], datetime] | None:
        record = self._metadata(key)
        if not record or record.get("kind") not in {"value", "universe"}:
            return None
        payload = self._download_verified(record)
        if payload is None:
            return None
        try:
            value = json.loads(payload.decode("utf-8"))
            if not isinstance(value, dict):
                return None
            return value, _record_time(record)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return None

    def put_value(self, key: str, value: dict[str, Any]) -> None:
        kind = "universe" if key.startswith("universe:") else "value"
        meta = value.get("meta", {}) if isinstance(value.get("meta"), dict) else {}
        provenance = value.get("provenance", {}) if isinstance(value.get("provenance"), dict) else {}
        self._publish(key, kind, json.dumps(value, default=str, separators=(",", ":")).encode("utf-8"),
                      "application/json", dict(meta or provenance), coverage_start=None, coverage_end=None,
                      row_count=len(value.get("items", [])) if isinstance(value.get("items"), list) else None,
                      constituents=value.get("items") if kind == "universe" else None)

    @contextmanager
    def refresh_lease(self, key: str) -> Iterator[bool]:
        lease = self._claim_lease(key)
        if lease is None:
            yield False
            return
        active = dict(self._leases.get())
        active[key] = lease
        token = self._leases.set(active)
        try:
            yield True
        finally:
            self._leases.reset(token)

    def _metadata(self, key: str) -> dict[str, Any] | None:
        response = self._request("GET", "/rest/v1/market_data_metadata", operation="metadata lookup",
                                 params={"dataset_key": f"eq.{key}", "select": "record"}, allow_not_found=True)
        if response is None:
            return None
        try:
            rows = response.json()
            if not isinstance(rows, list) or not rows:
                return None
            record = rows[0].get("record")
            if not isinstance(record, dict) or not self._REQUIRED_RECORD_FIELDS <= record.keys():
                return None
            if record.get("format_version") != 1 or record.get("bucket") != self.bucket:
                return None
            object_key = record.get("object_key")
            if (not isinstance(object_key, str) or not object_key.startswith(self.prefix + "/")
                    or any(part in {"", ".", ".."} for part in object_key.split("/"))
                    or "\\" in object_key or "%" in object_key
                    or not isinstance(record["quality_json"], dict)
                    or not isinstance(record["checksum_sha256"], str)
                    or len(record["checksum_sha256"]) != 64):
                return None
            _record_time(record)
            return record
        except (ValueError, TypeError, AttributeError):
            return None

    def _download_verified(self, record: dict[str, Any]) -> bytes | None:
        path = f"/storage/v1/object/{quote(self.bucket, safe='')}/{quote(str(record['object_key']), safe='/')}"
        response = self._request("GET", path, operation="artifact download", allow_not_found=True)
        if response is None:
            return None
        payload = response.content
        if hashlib.sha256(payload).hexdigest() != record["checksum_sha256"]:
            return None
        return payload

    def _claim_lease(self, key: str) -> dict[str, Any] | None:
        response = self._request("POST", "/rest/v1/rpc/claim_market_refresh_lease", operation="refresh lease",
                                 json={"p_dataset_key": key, "p_lease_seconds": 60})
        try:
            lease = response.json()
            if lease is None or not isinstance(lease, dict):
                return None
            if not {"lease_token", "lease_fence", "lease_expires_at"} <= lease.keys():
                return None
            return lease
        except ValueError:
            return None

    def _publish(self, key: str, kind: str, payload: bytes, content_type: str, quality: dict[str, Any], *,
                 coverage_start: Any, coverage_end: Any, row_count: int | None, constituents=None) -> None:
        lease = self._leases.get().get(key)
        if lease is None:
            raise RemoteCacheError("Remote market cache requires a refresh lease.")
        version = uuid4().hex
        object_key = f"{self.prefix}/{_safe_object_component(key)}/{version}.{'parquet' if kind == 'history' else 'json'}"
        checksum = hashlib.sha256(payload).hexdigest()
        upload_path = f"/storage/v1/object/{quote(self.bucket, safe='')}/{quote(object_key, safe='/')}"
        self._request("POST", upload_path, operation="artifact upload", content=payload,
                      headers={"Content-Type": content_type, "x-upsert": "false"})
        # Storage and Postgres are separate transactions. Verify uploaded bytes
        # before publishing the pointer; failed/unpublished objects are orphans.
        verified = self._request("GET", upload_path, operation="artifact verification")
        if hashlib.sha256(verified.content).hexdigest() != checksum:
            raise RemoteCacheError("Remote market cache upload checksum mismatch.")
        retrieved_at = iso_now()
        record = {
            "format_version": 1, "kind": kind, "bucket": self.bucket, "object_key": object_key,
            "object_version": version, "checksum_sha256": checksum, "content_type": content_type,
            "source": quality.get("source"), "observed_at": quality.get("as_of"),
            "retrieved_at": retrieved_at, "coverage_start": coverage_start,
            "coverage_end": coverage_end, "row_count": row_count, "quality_json": quality,
        }
        if constituents is not None:
            record["constituents"] = [
                {"symbol": item["symbol"].replace(".", "-"), "name": item["name"],
                 "sector": canonical_sector(item.get("gics_sector") or item.get("sector"))}
                for item in constituents
            ]
        response = self._request("POST", "/rest/v1/rpc/publish_market_dataset", operation="metadata publication",
                                 json={"p_dataset_key": key, "p_fence": lease["lease_fence"],
                                       "p_lease_token": lease["lease_token"], "p_record": record})
        try:
            if response.json() is not True:
                raise RemoteCacheError("Remote market cache rejected metadata publication.")
        except ValueError as exc:
            raise RemoteCacheError("Remote market cache returned an invalid publication response.") from exc

    def _request(self, method: str, path: str, *, operation: str, allow_not_found: bool = False, **kwargs: Any) -> httpx.Response | None:
        try:
            response = self._client.request(method, f"{self.base_url}{path}", **kwargs)
        except httpx.HTTPError as exc:
            raise RemoteCacheError(f"Remote market cache {operation} failed.") from exc
        if allow_not_found and response.status_code == 404:
            return None
        if response.is_error:
            raise RemoteCacheError(f"Remote market cache {operation} failed.")
        return response


def _record_time(record: dict[str, Any]) -> datetime:
    value = record.get("retrieved_at")
    if not isinstance(value, str):
        raise ValueError("metadata has no retrieval timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("metadata timestamp must be timezone aware")
    return parsed


def _safe_object_component(key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    readable = "".join(char if char.isalnum() else "-" for char in key).strip("-")[:48]
    return f"{readable or 'dataset'}-{digest}"
