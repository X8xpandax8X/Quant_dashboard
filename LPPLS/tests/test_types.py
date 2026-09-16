from __future__ import annotations

import pandas as pd
import pytest

from lppls.config import InstrumentConfig
from lppls.types import InstrumentAnalysis, ModelOutput


def test_model_output_prefers_explicit_composite_score() -> None:
    dates = pd.date_range("2024-01-01", periods=3, freq="W")
    output = ModelOutput(
        "test",
        "Test",
        pd.DataFrame(
            {"raw": [0.1, 0.2, 0.3], "composite": [0.4, None, 0.8]}, index=dates
        ),
    )

    assert output.composite_score.tolist() == [0.4, 0.8]
    assert output.latest_score == 0.8


def test_model_output_falls_back_to_numeric_mean() -> None:
    dates = pd.date_range("2024-01-01", periods=2, freq="W")
    output = ModelOutput(
        "test",
        "Test",
        pd.DataFrame(
            {"short": [0.2, 0.6], "long": [0.4, 1.0], "label": ["a", "b"]}, index=dates
        ),
    )

    assert output.composite_score.tolist() == pytest.approx([0.3, 0.8])
    assert output.latest_score == pytest.approx(0.8)


def test_instrument_analysis_exposes_source_date_range() -> None:
    prices = pd.Series(
        [10.0, 12.0],
        index=[pd.Timestamp("2000-01-02"), pd.Timestamp("2024-01-07")],
    )
    analysis = InstrumentAnalysis(
        InstrumentConfig("ABC", "Example", "#123456"), prices, models={}
    )

    assert analysis.first_date == pd.Timestamp("2000-01-02")
    assert analysis.latest_date == pd.Timestamp("2024-01-07")
