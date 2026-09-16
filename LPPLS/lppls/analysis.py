"""Application service that coordinates data with registered models."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import pandas as pd

from .config import InstrumentConfig
from .models.base import BubbleModel
from .types import InstrumentAnalysis


class AnalysisEngine:
    def __init__(self, models: Iterable[BubbleModel]) -> None:
        self.models = tuple(models)
        if not self.models:
            raise ValueError("At least one model is required")

    def run(
        self,
        instruments: Iterable[InstrumentConfig],
        price_data: Mapping[str, pd.Series],
    ) -> list[InstrumentAnalysis]:
        analyses: list[InstrumentAnalysis] = []
        for instrument in instruments:
            prices = price_data.get(instrument.symbol)
            if prices is None or prices.empty:
                continue
            outputs = {model.key: model.analyze(prices) for model in self.models}
            analyses.append(InstrumentAnalysis(instrument, prices, outputs))
        return analyses
