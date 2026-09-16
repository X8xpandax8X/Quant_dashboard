"""Offline-first market data access for Quant Stock.

The package deliberately has no dependency on the API application.  Its public
entry point is :class:`data_engine.service.DataService`.
"""

from .instruments import MARKETS
from .service import DataService, HistoryResult

__all__ = ["DataService", "HistoryResult", "MARKETS"]
