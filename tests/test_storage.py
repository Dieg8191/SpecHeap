"""Contract tests run against every storage adapter (memory and SQLite)."""

from __future__ import annotations

import pytest

from specheap.core.models import Item, ItemType, Status
from specheap.core.ports import Storage


def make_req(number: int = 1, **overrides: object) -> Item:
    data: dict[str, object] = {
        "id": f"REQ-{number:03d}",
        "type": ItemType.REQ,
        "title": "Lock account after failed logins",
        "parent": "FEAT-001",
        "body": "WHEN the user fails 3 times,\nTHE SYSTEM SHALL lock the account.\n",
    }
    data.update(overrides)
    return Item.model_validate(data)


def test_get_missing_returns_none(storage: Storage) -> None:
    assert storage.get("REQ-001") is None


def test_save_and_get_roundtrip(storage: Storage) -> None:
    item = make_req(status=Status.APPROVED, satisfies=[], verifies=[])
    storage.save(item)
    assert storage.get("REQ-001") == item


def test_body_with_fence_and_unicode_roundtrips(storage: Storage) -> None:
    item = make_req(body="---\nNot a fence: Ã±andÃº âœ“\n---\n", title="TÃ­tulo con acentos: Ã±")
    storage.save(item)
    assert storage.get("REQ-001") == item


def test_empty_body_roundtrips(storage: Storage) -> None:
    item = make_req(body="")
    storage.save(item)
    assert storage.get("REQ-001") == item


def test_returned_items_are_independent_copies(storage: Storage) -> None:
    storage.save(make_req())
    fetched = storage.get("REQ-001")
    assert fetched is not None
    fetched.title = "Changed locally"
    again = storage.get("REQ-001")
    assert again is not None and again.title != "Changed locally"


def test_all_and_next_number(storage: Storage) -> None:
    assert storage.next_number(ItemType.REQ) == 1
    storage.save(make_req(1))
    storage.save(make_req(5))
    assert {item.id for item in storage.all()} == {"REQ-001", "REQ-005"}
    assert storage.next_number(ItemType.REQ) == 6
    assert storage.next_number(ItemType.SPEC) == 1


def test_save_overwrites(storage: Storage) -> None:
    storage.save(make_req())
    storage.save(make_req(title="New title"))
    fetched = storage.get("REQ-001")
    assert fetched is not None and fetched.title == "New title"
    assert len(storage.all()) == 1


def test_append_log(storage: Storage) -> None:
    storage.append_log({"action": "a"})
    storage.append_log({"action": "b", "id": "REQ-001", "extra": ["Ã±", 1]})
    assert storage.log_entries() == [
        {"action": "a"},
        {"action": "b", "id": "REQ-001", "extra": ["Ã±", 1]},
    ]


def test_links_and_verification_fields_roundtrip(storage: Storage) -> None:
    spec = Item.model_validate(
        {
            "id": "SPEC-001",
            "type": ItemType.SPEC,
            "title": "Counter",
            "parent": "REQ-001",
            "satisfies": ["REQ-003", "REQ-002"],  # Order is preserved.
        }
    )
    ver = Item.model_validate(
        {
            "id": "VER-001",
            "type": ItemType.VERIFICATION,
            "title": "Lock test",
            "parent": "REQ-001",
            "verifies": ["SPEC-001", "REQ-002"],
            "result": "fail",
            "evidence": "expected 3, got 2",
            "run_ref": "run-7",
        }
    )
    storage.save(spec)
    storage.save(ver)
    assert storage.get("SPEC-001") == spec
    assert storage.get("VER-001") == ver
    assert sorted(storage.all(), key=lambda i: i.id) == [spec, ver]


def test_removing_links_persists(storage: Storage) -> None:
    spec = Item.model_validate(
        {"id": "SPEC-001", "type": ItemType.SPEC, "title": "S", "parent": "REQ-001",
         "satisfies": ["REQ-002"]}
    )
    storage.save(spec)
    spec.satisfies.clear()
    storage.save(spec)
    fetched = storage.get("SPEC-001")
    assert fetched is not None and fetched.satisfies == []


# ------------------------------------------------------------ transactions


def test_transaction_commits_on_success(storage: Storage) -> None:
    with storage.transaction():
        storage.save(make_req(1))
        storage.append_log({"action": "create"})
    assert storage.get("REQ-001") is not None
    assert storage.log_entries() == [{"action": "create"}]


def test_transaction_rolls_back_items_and_log_on_error(storage: Storage) -> None:
    storage.save(make_req(1))
    with pytest.raises(RuntimeError):
        with storage.transaction():
            storage.save(make_req(1, title="Changed"))
            storage.save(make_req(2))
            storage.append_log({"action": "lost"})
            raise RuntimeError("boom")
    original = storage.get("REQ-001")
    assert original is not None and original.title == "Lock account after failed logins"
    assert storage.get("REQ-002") is None
    assert storage.log_entries() == []


def test_nested_transactions_join_the_outer_one(storage: Storage) -> None:
    with pytest.raises(RuntimeError):
        with storage.transaction():
            with storage.transaction():
                storage.save(make_req(1))
            storage.save(make_req(2))
            raise RuntimeError("boom")
    assert storage.all() == []


def test_reads_inside_a_transaction_see_its_own_writes(storage: Storage) -> None:
    with storage.transaction():
        assert storage.next_number(ItemType.REQ) == 1
        storage.save(make_req(1))
        assert storage.next_number(ItemType.REQ) == 2
        assert [i.id for i in storage.all()] == ["REQ-001"]


def test_storage_is_usable_after_a_rolled_back_transaction(storage: Storage) -> None:
    with pytest.raises(RuntimeError):
        with storage.transaction():
            storage.save(make_req(1))
            raise RuntimeError("boom")
    with storage.transaction():
        storage.save(make_req(1))
    assert storage.get("REQ-001") is not None
