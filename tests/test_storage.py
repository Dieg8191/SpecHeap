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


def test_append_log(storage: Storage, tmp_path: Path) -> None:
    storage.append_log({"action": "a"})
    storage.append_log({"action": "b"})
    if isinstance(storage, FileSystemStorage):
        lines = (storage.data_dir / "log.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2 and '"action": "b"' in lines[1]


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
