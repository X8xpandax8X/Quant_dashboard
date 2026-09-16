"""Interface implemented by every bubble-analysis model."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from ..types import ModelOutput


class BubbleModel(ABC):
    key: str
    name: str

    @abstractmethod
    def analyze(self, prices: pd.Series) -> ModelOutput:
        """Analyze a positive, chronological price series."""
