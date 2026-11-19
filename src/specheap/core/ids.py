"""Stable, human-readable item identifiers such as ``REQ-012``."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from specheap.core.errors import ValidationFailedError

if TYPE_CHECKING:
    from specheap.core.models import ItemType

_ID_PATTERN = re.compile(r"^(?P<prefix>[A-Z]+)-(?P<number>\d{1,6})$")


def _prefixes() -> dict[str, ItemType]:
    # Imported lazily to avoid a circular import with ``models``.
    from specheap.core.models import ItemType

    return {
        "EPIC": ItemType.EPIC,
        "FEAT": ItemType.FEATURE,
        "REQ": ItemType.REQ,
        "SPEC": ItemType.SPEC,
        "VER": ItemType.VERIFICATION,
    }


def format_id(item_type: ItemType, number: int) -> str:
    """Build an identifier, e.g. ``format_id(ItemType.REQ, 12) == "REQ-012"``."""
    if number < 1:
        raise ValidationFailedError("Identifier numbers start at 1.", field="number")
    for prefix, known_type in _prefixes().items():
        if known_type == item_type:
            return f"{prefix}-{number:03d}"
    raise ValidationFailedError(f"Unknown item type: {item_type!r}.", field="type")


def parse_id(item_id: str) -> tuple[ItemType, int]:
    """Split an identifier into its item type and number.

    Raises:
        ValidationFailedError: if the identifier is malformed or uses an unknown prefix.
    """
    match = _ID_PATTERN.match(item_id)
    if match is None:
        raise ValidationFailedError(
            f"Malformed identifier: {item_id!r}.",
            hint="Identifiers look like REQ-012 (PREFIX-NUMBER).",
            field="id",
        )
    prefixes = _prefixes()
    prefix = match.group("prefix")
    if prefix not in prefixes:
        raise ValidationFailedError(
            f"Unknown identifier prefix: {prefix!r}.",
            hint=f"Valid prefixes: {', '.join(sorted(prefixes))}.",
            field="id",
        )
    return prefixes[prefix], int(match.group("number"))
