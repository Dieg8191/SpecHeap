"""Ports: interfaces the core depends on and that adapters implement."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Protocol

from specheap.core.models import Item, ItemType


class Storage(Protocol):
    """Persistence port for items and the audit log.

    Implementations must return independent copies from ``get`` and ``all`` so callers can
    mutate them freely before calling ``save``.
    """

    def get(self, item_id: str) -> Item | None:
        """Return the item with the given id, or ``None`` if it does not exist."""
        ...

    def save(self, item: Item) -> None:
        """Create or replace an item."""
        ...

    def all(self) -> list[Item]:
        """Return every stored item."""
        ...

    def next_number(self, item_type: ItemType) -> int:
        """Return the next unused identifier number for the given type.

        Only reliable inside a ``transaction()``: the number must be saved before the
        transaction ends so that concurrent writers cannot receive the same one.
        """
        ...

    def append_log(self, entry: dict[str, Any]) -> None:
        """Append one entry to the audit log."""
        ...

    def log_entries(self) -> list[dict[str, Any]]:
        """Return the audit log, oldest entry first."""
        ...

    def transaction(self) -> AbstractContextManager[None]:
        """Group several writes so they either all happen or none do.

        Writers are serialized: while a transaction is open, other writers wait. Transactions
        are re-entrant: a nested ``transaction()`` joins the outer one, and only an exception
        that escapes the outermost block rolls everything back.
        """
        ...
