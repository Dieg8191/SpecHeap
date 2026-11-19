"""In-memory storage, mainly for tests and ephemeral sessions."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from specheap.core.ids import parse_id
from specheap.core.models import Item, ItemType


class MemoryStorage:
    """Keeps items and the audit log in process memory. Not safe for concurrent threads."""

    def __init__(self) -> None:
        self._items: dict[str, Item] = {}
        self.log: list[dict[str, Any]] = []
        self._depth = 0

    def get(self, item_id: str) -> Item | None:
        item = self._items.get(item_id)
        return item.model_copy(deep=True) if item is not None else None

    def save(self, item: Item) -> None:
        self._items[item.id] = item.model_copy(deep=True)

    def all(self) -> list[Item]:
        return [item.model_copy(deep=True) for item in self._items.values()]

    def next_number(self, item_type: ItemType) -> int:
        return next_number(self._items.values(), item_type)

    def append_log(self, entry: dict[str, Any]) -> None:
        self.log.append(dict(entry))

    def log_entries(self) -> list[dict[str, Any]]:
        return [dict(entry) for entry in self.log]

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Snapshot on entry and restore it if the outermost block raises."""
        if self._depth > 0:
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
            return
        items = {key: value.model_copy(deep=True) for key, value in self._items.items()}
        log = [dict(entry) for entry in self.log]
        self._depth = 1
        try:
            yield
        except BaseException:
            self._items = items
            self.log[:] = log
            raise
        finally:
            self._depth = 0


def next_number(items: Any, item_type: ItemType) -> int:
    """The next free identifier number among ``items`` for ``item_type``."""
    numbers = [parse_id(i.id)[1] for i in items if i.type is item_type]
    return max(numbers, default=0) + 1
