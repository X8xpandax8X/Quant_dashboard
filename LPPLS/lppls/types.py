"""Shared result types consumed by models and the dashboard."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from .config import InstrumentConfig


@dataclass(slots=True)
class FitCurve:
    key: str
    label: str
    color: str
    dash: str
    values: pd.Series


@dataclass(slots=True)
class ModelOutput:
    """Model-neutral payload so future models can reuse the same dashboard."""

    model_key: str
    model_name: str
    score_frame: pd.DataFrame
    fit_curves: list[FitCurve] = field(default_factory=list)
    forecast_frame: pd.DataFrame = field(default_factory=pd.DataFrame)
    parameter_rows: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def composite_score(self) -> pd.Series:
        if "composite" in self.score_frame:
            return self.score_frame["composite"].dropna()
        numeric = self.score_frame.select_dtypes("number")
        return numeric.mean(axis=1, skipna=True).dropna()

    @property
    def latest_score(self) -> float | None:
        score = self.composite_score
        return None if score.empty else float(score.iloc[-1])


@dataclass(slots=True)
class InstrumentAnalysis:
    instrument: InstrumentConfig
    prices: pd.Series
    models: dict[str, ModelOutput]

    @property
    def first_date(self) -> pd.Timestamp:
        return pd.Timestamp(self.prices.index[0])

    @property
    def latest_date(self) -> pd.Timestamp:
        return pd.Timestamp(self.prices.index[-1])
