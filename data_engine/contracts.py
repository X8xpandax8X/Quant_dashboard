"""Injectable boundaries used by the data service.

The cache protocol deliberately contains no user identity.  It is only for
shared market artifacts and must never be used for private portfolio state.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from typing import Any, Protocol

import pandas as pd

from .cache import CachedHistory


class MarketCache(Protocol):
    """Versioned market cache used by :class:`DataService`."""

    is_remote: bool

    def get_history(self, key: str) -> CachedHistory | None: ...

    def put_history(self, key: str, frame: pd.DataFrame, meta: dict[str, Any]) -> None: ...

    def get_value(self, key: str) -> tuple[dict[str, Any], datetime] | None: ...

    def put_value(self, key: str, value: dict[str, Any]) -> None: ...

    def refresh_lease(self, key: str) -> AbstractContextManager[bool]: ...
