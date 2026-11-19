"""Tests for identifiers and domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from specheap.core import (
    InvalidParentError,
    Item,
    ItemType,
    ValidationFailedError,
    format_id,
    parse_id,
    validate_parent,
)


def test_format_and_parse_roundtrip() -> None:
    assert format_id(ItemType.REQ, 12) == "REQ-012"
    assert parse_id("REQ-012") == (ItemType.REQ, 12)
    assert parse_id(format_id(ItemType.FEATURE, 3)) == (ItemType.FEATURE, 3)


@pytest.mark.parametrize("bad", ["req-012", "REQ012", "REQ-", "FOO-001", "", "REQ-0000001"])
def test_parse_id_rejects_malformed(bad: str) -> None:
    with pytest.raises(ValidationFailedError):
        parse_id(bad)


def test_format_id_rejects_zero() -> None:
    with pytest.raises(ValidationFailedError):
        format_id(ItemType.REQ, 0)


@pytest.mark.parametrize(
    ("child", "parent"),
    [
        (ItemType.EPIC, None),
        (ItemType.FEATURE, "EPIC-001"),
        (ItemType.REQ, "FEAT-001"),
        (ItemType.SPEC, "REQ-001"),
        (ItemType.VERIFICATION, "REQ-001"),
        (ItemType.VERIFICATION, "SPEC-001"),
    ],
)
def test_valid_parents(child: ItemType, parent: str | None) -> None:
    validate_parent(child, parent)


@pytest.mark.parametrize(
    ("child", "parent"),
    [
        (ItemType.EPIC, "EPIC-001"),
        (ItemType.FEATURE, None),
        (ItemType.FEATURE, "REQ-001"),
        (ItemType.REQ, "EPIC-001"),
        (ItemType.SPEC, "FEAT-001"),
        (ItemType.VERIFICATION, "FEAT-001"),
    ],
)
def test_invalid_parents(child: ItemType, parent: str | None) -> None:
    with pytest.raises(InvalidParentError) as exc:
        validate_parent(child, parent)
    assert exc.value.code == "INVALID_PARENT"
    assert exc.value.hint


def test_item_defaults_and_revision_changes_with_content() -> None:
    item = Item(id="REQ-001", type=ItemType.REQ, title="Lock account", parent="FEAT-001")
    assert item.status.value == "draft"
    before = item.revision
    item.title = "Lock account after failures"
    assert item.revision != before


def test_item_revision_is_stable_for_equal_content() -> None:
    a = Item(id="REQ-001", type=ItemType.REQ, title="X", parent="FEAT-001")
    b = Item(id="REQ-001", type=ItemType.REQ, title="X", parent="FEAT-001")
    assert a.revision == b.revision


def test_item_rejects_malformed_id_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Item(id="nope", type=ItemType.REQ, title="X")
    with pytest.raises(ValidationError):
        Item(id="REQ-001", type=ItemType.REQ, title="X", unknown="field")  # type: ignore[call-arg]


def test_error_serialization() -> None:
    with pytest.raises(InvalidParentError) as exc:
        validate_parent(ItemType.REQ, None)
    payload = exc.value.to_dict()
    assert payload["code"] == "INVALID_PARENT"
    assert "message" in payload and "hint" in payload
