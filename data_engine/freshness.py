"""Central, clock-injectable cache freshness rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable


Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class FreshnessPolicy:
    """Freshness policy independent of providers, storage, and web requests."""

    clock: Clock = utc_now
    history_ttls: dict[str, timedelta] = field(default_factory=lambda: {
        "1D": timedelta(minutes=5), "5D": timedelta(minutes=5),
        "1M": timedelta(minutes=15), "1Y": timedelta(minutes=15),
    })
    fundamentals_ttl: timedelta = timedelta(days=1)
    risk_free_rate_ttl: timedelta = timedelta(days=1)
    universe_ttl: timedelta = timedelta(days=1)
    failure_ttl: timedelta = timedelta(minutes=5)

    def history_ttl(self, timeframe: str) -> timedelta:
        return self.history_ttls[timeframe]

    def is_fresh(self, refreshed_at: datetime, ttl: timedelta) -> bool:
        if refreshed_at.tzinfo is None:
            return False
        age = self.clock() - refreshed_at
        return timedelta(0) <= age <= ttl

    def value_is_fresh(self, value: dict[str, object], refreshed_at: datetime, ttl: timedelta) -> bool:
        status = value.get("meta", {})
        status = status.get("status") if isinstance(status, dict) else None
        return self.is_fresh(refreshed_at, self.failure_ttl if status == "unavailable" else ttl)
