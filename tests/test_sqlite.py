"""SQLite adapter: schema, versioning, isolation and real concurrency."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from specheap.core.errors import RevisionConflictError, StorageError
from specheap.core.models import Actor, Item, ItemType
from specheap.core.service import Service
from specheap.storage.sqlite import SCHEMA_VERSION, SQLiteStorage, project_database_path


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / ".specheap" / "specheap.db"


@pytest.fixture
def sqlite_storage(db_path: Path) -> Iterator[SQLiteStorage]:
    storage = SQLiteStorage(db_path)
    yield storage
    storage.close()


def epic(number: int, title: str = "Epic") -> Item:
    return Item.model_validate({"id": f"EPIC-{number:03d}", "type": ItemType.EPIC, "title": title})


# ------------------------------------------------------------------- schema


def test_creates_directory_schema_and_wal(db_path: Path, sqlite_storage: SQLiteStorage) -> None:
    assert db_path.is_file()
    raw = sqlite3.connect(db_path)
    try:
        assert raw.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert raw.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        tables = {r[0] for r in raw.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        raw.close()
    assert {"items", "links", "audit_log"} <= tables


def test_project_database_path(tmp_path: Path) -> None:
    assert project_database_path(tmp_path) == tmp_path / ".specheap" / "specheap.db"
    storage = SQLiteStorage.for_project(tmp_path)
    try:
        assert (tmp_path / ".specheap" / "specheap.db").is_file()
    finally:
        storage.close()


def test_data_survives_reopening(db_path: Path) -> None:
    first = SQLiteStorage(db_path)
    first.save(epic(1, "Persistent"))
    first.append_log({"action": "create_item", "id": "EPIC-001"})
    first.close()

    second = SQLiteStorage(db_path)
    try:
        item = second.get("EPIC-001")
        assert item is not None and item.title == "Persistent"
        assert second.log_entries() == [{"action": "create_item", "id": "EPIC-001"}]
    finally:
        second.close()


def test_database_from_a_newer_version_is_refused(db_path: Path) -> None:
    SQLiteStorage(db_path).close()
    raw = sqlite3.connect(db_path)
    raw.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    raw.commit()
    raw.close()
    with pytest.raises(StorageError) as exc:
        SQLiteStorage(db_path)
    assert "Upgrade SpecHeap" in (exc.value.hint or "")


def test_a_file_that_is_not_a_database_is_a_clear_error(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True)
    db_path.write_bytes(b"this is definitely not a sqlite database" * 20)
    with pytest.raises(StorageError) as exc:
        SQLiteStorage(db_path)
    assert exc.value.code == "STORAGE_ERROR" and str(db_path) in exc.value.message


# ---------------------------------------------------------------- isolation


def test_other_connections_do_not_see_uncommitted_changes(
    db_path: Path, sqlite_storage: SQLiteStorage
) -> None:
    other = SQLiteStorage(db_path)
    try:
        with sqlite_storage.transaction():
            sqlite_storage.save(epic(1))
            assert sqlite_storage.get("EPIC-001") is not None
            assert other.get("EPIC-001") is None  # Not committed yet.
        assert other.get("EPIC-001") is not None
    finally:
        other.close()


def test_one_storage_can_be_used_from_several_threads(sqlite_storage: SQLiteStorage) -> None:
    def create(n: int) -> str:
        service = Service(sqlite_storage, Actor.AGENT)
        return service.create_item(ItemType.EPIC, f"Epic {n}").id

    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(create, range(20)))
    assert sorted(ids) == [f"EPIC-{n:03d}" for n in range(1, 21)]


# -------------------------------------------------------------- concurrency


def test_concurrent_writers_receive_unique_sequential_ids(
    db_path: Path, sqlite_storage: SQLiteStorage
) -> None:
    """Separate connections, as the MCP server, the UI and the CLI would have."""
    writers, per_writer = 8, 10
    start = threading.Barrier(writers)

    def work(worker: int) -> list[str]:
        storage = SQLiteStorage(db_path)
        try:
            service = Service(storage, Actor.AGENT)
            start.wait()
            return [
                service.create_item(ItemType.EPIC, f"Epic {worker}-{n}").id
                for n in range(per_writer)
            ]
        finally:
            storage.close()

    with ThreadPoolExecutor(max_workers=writers) as pool:
        created = [item_id for ids in pool.map(work, range(writers)) for item_id in ids]

    total = writers * per_writer
    assert len(created) == len(set(created)) == total
    assert sorted(created) == [f"EPIC-{n:03d}" for n in range(1, total + 1)]
    assert len(sqlite_storage.all()) == total


def test_concurrent_edits_with_the_same_revision_have_exactly_one_winner(
    db_path: Path, sqlite_storage: SQLiteStorage
) -> None:
    created = Service(sqlite_storage, Actor.HUMAN).create_item(ItemType.EPIC, "Original")
    editors = 8
    start = threading.Barrier(editors)

    def edit(worker: int) -> str:
        storage = SQLiteStorage(db_path)
        try:
            service = Service(storage, Actor.AGENT)
            start.wait()
            try:
                service.update_item(created.id, {"title": f"Edit {worker}"}, created.revision)
            except RevisionConflictError:
                return "conflict"
            return "won"
        finally:
            storage.close()

    with ThreadPoolExecutor(max_workers=editors) as pool:
        outcomes = list(pool.map(edit, range(editors)))

    assert outcomes.count("won") == 1
    assert outcomes.count("conflict") == editors - 1
    final = sqlite_storage.get(created.id)
    assert final is not None and final.title.startswith("Edit ")
    updates = [e for e in sqlite_storage.log_entries() if e["action"] == "update_item"]
    assert len(updates) == 1
