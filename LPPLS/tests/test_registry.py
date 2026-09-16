from __future__ import annotations

import pandas as pd
import pytest

from lppls.models.base import BubbleModel
from lppls.models.registry import ModelRegistry
from lppls.types import ModelOutput


class DummyModel(BubbleModel):
    key = "dummy"
    name = "Dummy"

    def analyze(self, prices: pd.Series) -> ModelOutput:
        return ModelOutput(self.key, self.name, pd.DataFrame({"composite": prices * 0}))


def test_registry_normalizes_keys_and_creates_fresh_models() -> None:
    registry = ModelRegistry()
    registry.register(" Dummy ", DummyModel)

    first = registry.create("DUMMY")
    second = registry.create_many()[0]

    assert registry.keys() == ("dummy",)
    assert isinstance(first, DummyModel)
    assert isinstance(second, DummyModel)
    assert first is not second


def test_registry_rejects_empty_duplicate_and_unknown_keys() -> None:
    registry = ModelRegistry()
    with pytest.raises(ValueError, match="empty"):
        registry.register(" ", DummyModel)

    registry.register("dummy", DummyModel)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("DUMMY", DummyModel)
    with pytest.raises(KeyError, match="available: dummy"):
        registry.create("missing")
