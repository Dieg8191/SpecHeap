"""In-memory storage, mainly for tests and ephemeral sessions."""

from __future__ import annotations

from typing import Any

from specheap.core.ids import parse_id
from specheap.core.models import Item, ItemType


class MemoryStorage:
    """Keeps items and the audit log in process memory."""

    def __init__(self) -> None:
        self._items: dict[str, Item] = {}
        self.log: list[dict[str, Any]] = []

    def get(self, item_id: str) -> Item | None:
        item = self._items.get(item_id)
        return item.model_copy(deep=True) if item is not None else None

    def save(self, item: Item) -> None:
        self._items[item.id] = item.model_copy(deep=True)

    def all(self) -> list[Item]:
        return [item.model_copy(deep=True) for item in self._items.values()]

    def next_number(self, item_type: ItemType) -> int:
        return _next_number(self._items.values(), item_type)

    def append_log(self, entry: dict[str, Any]) -> None:
        self.log.append(dict(entry))


def _next_number(items: Any, item_type: ItemType) -> int:
    numbers = [parse_id(i.id)[1] for i in items if i.type is item_type]
    return max(numbers, default=0) + 1
