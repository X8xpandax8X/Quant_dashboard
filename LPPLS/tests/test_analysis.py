from __future__ import annotations

import pandas as pd
import pytest

from lppls.analysis import AnalysisEngine
from lppls.config import InstrumentConfig
from lppls.models.base import BubbleModel
from lppls.types import ModelOutput


class ConstantModel(BubbleModel):
    def __init__(self, key: str, value: float) -> None:
        self.key = key
        self.name = key.title()
        self.value = value

    def analyze(self, prices: pd.Series) -> ModelOutput:
        scores = pd.DataFrame(
            {"composite": [self.value] * len(prices)},
            index=prices.index,
        )
        return ModelOutput(self.key, self.name, scores)


def test_analysis_engine_is_model_neutral_and_skips_missing_data() -> None:
    available = InstrumentConfig("AAA", "Available", "#111111")
    missing = InstrumentConfig("BBB", "Missing", "#222222")
    prices = pd.Series(
        [10.0, 11.0],
        index=pd.date_range("2024-01-07", periods=2, freq="W"),
        name="close",
    )
    engine = AnalysisEngine(
        (ConstantModel("first", 0.25), ConstantModel("second", 0.75))
    )

    results = engine.run((available, missing), {"AAA": prices})

    assert len(results) == 1
    assert results[0].instrument is available
    assert set(results[0].models) == {"first", "second"}
    assert results[0].models["second"].latest_score == 0.75


def test_analysis_engine_requires_at_least_one_model() -> None:
    with pytest.raises(ValueError, match="At least one model"):
        AnalysisEngine(())
