"""Read-only view over the item graph.

Links are stored on the child side only, so this class computes the inverse lookups
(children, linked items, dependents) needed by the service.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable

from specheap.core.models import Item, ItemType


class Graph:
    """In-memory snapshot of the traceability graph."""

    def __init__(self, items: Iterable[Item]) -> None:
        self._items: dict[str, Item] = {item.id: item for item in items}
        self._children: dict[str, list[str]] = defaultdict(list)
        self._linked_from: dict[str, list[str]] = defaultdict(list)
        for item in self._items.values():
            if item.parent is not None:
                self._children[item.parent].append(item.id)
            for target in (*item.satisfies, *item.verifies):
                self._linked_from[target].append(item.id)

    def get(self, item_id: str) -> Item | None:
        return self._items.get(item_id)

    def items(self, item_type: ItemType | None = None) -> list[Item]:
        """All items, optionally restricted to one type."""
        return [i for i in self._items.values() if item_type is None or i.type is item_type]

    def specs_for(self, req_id: str) -> list[Item]:
        """Specs that satisfy a requirement (as parent or through a ``satisfies`` link)."""
        return [i for i in self._related(req_id) if i.type is ItemType.SPEC]

    def verifications_for(self, item_id: str) -> list[Item]:
        """Verifications attached to a requirement or spec (parent or ``verifies`` link)."""
        return [i for i in self._related(item_id) if i.type is ItemType.VERIFICATION]

    def dependents(self, item_id: str) -> set[str]:
        """Ids of every item that transitively depends on ``item_id`` (excluding itself)."""
        seen: set[str] = set()
        queue = deque([item_id])
        while queue:
            current = queue.popleft()
            for nxt in (*self._children[current], *self._linked_from[current]):
                if nxt not in seen and nxt != item_id:
                    seen.add(nxt)
                    queue.append(nxt)
        return seen

    def ancestors(self, item_id: str) -> list[Item]:
        """Parent chain from the root (epic) down to the direct parent."""
        chain: list[Item] = []
        seen = {item_id}
        current = self._items.get(item_id)
        while current is not None and current.parent is not None and current.parent not in seen:
            parent = self._items.get(current.parent)
            if parent is None:
                break
            chain.append(parent)
            seen.add(parent.id)
            current = parent
        return list(reversed(chain))

    def upstream(self, item_id: str) -> list[Item]:
        """Everything ``item_id`` traces back to (parents and link targets)."""
        seen: set[str] = {item_id}
        queue = deque([item_id])
        while queue:
            item = self._items.get(queue.popleft())
            if item is None:
                continue
            parents = [item.parent] if item.parent else []
            for target in (*parents, *item.satisfies, *item.verifies):
                if target not in seen and target in self._items:
                    seen.add(target)
                    queue.append(target)
        seen.discard(item_id)
        return [self._items[i] for i in seen]

    def descendants(self, item_id: str, depth: int | None = None) -> list[Item]:
        """Items below ``item_id`` (children and linked items), up to ``depth`` levels."""
        seen: set[str] = {item_id}
        level = [item_id]
        found: list[Item] = []
        remaining = depth
        while level and (remaining is None or remaining > 0):
            next_level: list[str] = []
            for current in level:
                for nxt in (*self._children[current], *self._linked_from[current]):
                    if nxt not in seen and nxt in self._items:
                        seen.add(nxt)
                        next_level.append(nxt)
                        found.append(self._items[nxt])
            level = next_level
            if remaining is not None:
                remaining -= 1
        return found

    def _related(self, item_id: str) -> list[Item]:
        ids = dict.fromkeys((*self._children[item_id], *self._linked_from[item_id]))
        return [self._items[i] for i in ids if i in self._items]
