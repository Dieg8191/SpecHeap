"""Contract tests run against every storage adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from specheap.core.errors import ValidationFailedError
from specheap.core.models import Item, ItemType, Status
from specheap.core.ports import Storage
from specheap.storage import FileSystemStorage


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
    item = make_req(body="---\nNot a fence: ñandú ✓\n---\n", title="Título con acentos: ñ")
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
    storage.append_log({"action": "b", "id": "REQ-001", "extra": ["ñ", 1]})
    assert storage.log_entries() == [
        {"action": "a"},
        {"action": "b", "id": "REQ-001", "extra": ["ñ", 1]},
    ]


def test_fs_log_is_one_json_line_per_entry(tmp_path: Path) -> None:
    storage = FileSystemStorage(tmp_path)
    storage.append_log({"action": "a"})
    storage.append_log({"action": "b"})
    lines = (storage.data_dir / "log.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and '"action": "b"' in lines[1]


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


def test_transaction_commits_on_success(atomic_storage: Storage) -> None:
    with atomic_storage.transaction():
        atomic_storage.save(make_req(1))
        atomic_storage.append_log({"action": "create"})
    assert atomic_storage.get("REQ-001") is not None
    assert atomic_storage.log_entries() == [{"action": "create"}]


def test_transaction_rolls_back_items_and_log_on_error(atomic_storage: Storage) -> None:
    atomic_storage.save(make_req(1))
    with pytest.raises(RuntimeError):
        with atomic_storage.transaction():
            atomic_storage.save(make_req(1, title="Changed"))
            atomic_storage.save(make_req(2))
            atomic_storage.append_log({"action": "lost"})
            raise RuntimeError("boom")
    original = atomic_storage.get("REQ-001")
    assert original is not None and original.title == "Lock account after failed logins"
    assert atomic_storage.get("REQ-002") is None
    assert atomic_storage.log_entries() == []


def test_nested_transactions_join_the_outer_one(atomic_storage: Storage) -> None:
    with pytest.raises(RuntimeError):
        with atomic_storage.transaction():
            with atomic_storage.transaction():
                atomic_storage.save(make_req(1))
            atomic_storage.save(make_req(2))
            raise RuntimeError("boom")
    assert atomic_storage.all() == []


def test_reads_inside_a_transaction_see_its_own_writes(atomic_storage: Storage) -> None:
    with atomic_storage.transaction():
        assert atomic_storage.next_number(ItemType.REQ) == 1
        atomic_storage.save(make_req(1))
        assert atomic_storage.next_number(ItemType.REQ) == 2
        assert [i.id for i in atomic_storage.all()] == ["REQ-001"]


def test_storage_is_usable_after_a_rolled_back_transaction(atomic_storage: Storage) -> None:
    with pytest.raises(RuntimeError):
        with atomic_storage.transaction():
            atomic_storage.save(make_req(1))
            raise RuntimeError("boom")
    with atomic_storage.transaction():
        atomic_storage.save(make_req(1))
    assert atomic_storage.get("REQ-001") is not None


def test_fs_layout_is_human_readable(tmp_path: Path) -> None:
    storage = FileSystemStorage(tmp_path)
    storage.save(make_req())
    text = (tmp_path / ".specheap" / "reqs" / "REQ-001.md").read_text(encoding="utf-8")
    assert text.startswith("---\nid: REQ-001\ntype: req\n")
    assert text.endswith("THE SYSTEM SHALL lock the account.\n")


def test_fs_rejects_corrupt_files(tmp_path: Path) -> None:
    storage = FileSystemStorage(tmp_path)
    storage.init()
    (tmp_path / ".specheap" / "reqs" / "REQ-001.md").write_text("no frontmatter", encoding="utf-8")
    with pytest.raises(ValidationFailedError) as exc:
        storage.get("REQ-001")
    assert "path" in exc.value.details
