"""Small model registry; an Agent-based model can register without UI changes."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from .base import BubbleModel


ModelFactory = Callable[[], BubbleModel]


class ModelRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, ModelFactory] = {}

    def register(self, key: str, factory: ModelFactory) -> None:
        normalized = key.strip().lower()
        if not normalized:
            raise ValueError("Model key cannot be empty")
        if normalized in self._factories:
            raise ValueError(f"Model already registered: {normalized}")
        self._factories[normalized] = factory

    def create(self, key: str) -> BubbleModel:
        try:
            return self._factories[key.strip().lower()]()
        except KeyError as exc:
            available = ", ".join(self.keys()) or "none"
            raise KeyError(f"Unknown model {key!r}; available: {available}") from exc

    def keys(self) -> tuple[str, ...]:
        return tuple(self._factories)

    def create_many(self, keys: Iterable[str] | None = None) -> list[BubbleModel]:
        selected = self.keys() if keys is None else tuple(keys)
        return [self.create(key) for key in selected]
