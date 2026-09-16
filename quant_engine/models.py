"""Explicit opt-in extension boundary; importing this module never loads LPPLS."""
from typing import Protocol

import pandas as pd

from .contracts import JSONValue


class ResearchModel(Protocol):
    name: str

    def analyze(self, prices: pd.DataFrame) -> dict[str, JSONValue]:
        """Return JSON-safe results without modifying input prices."""
        ...


class ModelRegistry:
    def __init__(self) -> None:
        self._models: dict[str, ResearchModel] = {}

    def register(self, model: ResearchModel) -> None:
        if not model.name or model.name in self._models:
            raise ValueError("Model name must be nonempty and unique")
        self._models[model.name] = model

    def get(self, name: str) -> ResearchModel:
        return self._models[name]

    def names(self) -> tuple[str, ...]:
        return tuple(self._models)
