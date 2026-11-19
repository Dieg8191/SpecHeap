"""Tests for the command line interface."""

from __future__ import annotations

from pathlib import Path

import pytest

from specheap.cli import main
from specheap.core.models import Actor, ItemType, Status
from specheap.core.service import Service
from specheap.storage import FileSystemStorage, SQLiteStorage, project_database_path


def legacy_workspace(root: Path) -> FileSystemStorage:
    """An old markdown workspace with a small, reviewed chain of items."""
    storage = FileSystemStorage(root)
    storage.init()
    agent = Service(storage, Actor.AGENT)
    human = Service(storage, Actor.HUMAN)
    epic = agent.create_item(ItemType.EPIC, "Auth", body="Users sign in.")
    feat = agent.create_item(ItemType.FEATURE, "Login", parent_id=epic.id)
    req = agent.create_item(ItemType.REQ, "Lock account", parent_id=feat.id, body="Body ñ\n---\nx")
    spec = agent.create_item(ItemType.SPEC, "Counter", parent_id=req.id)
    agent.create_item(ItemType.VERIFICATION, "Lock test", parent_id=req.id)
    agent.link_items("VER-001", spec.id, "verifies")
    agent.propose_item(req.id)
    human.approve_item(req.id)
    return storage


def open_db(root: Path) -> SQLiteStorage:
    return SQLiteStorage.for_project(root)


def test_commands_require_init(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["gaps", "--root", str(tmp_path)]) == 2
    assert "specheap init" in capsys.readouterr().err


def test_old_markdown_workspaces_are_pointed_to_import(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    legacy_workspace(tmp_path)
    assert main(["gaps", "--root", str(tmp_path)]) == 2
    assert "specheap import" in capsys.readouterr().err


def test_init_creates_the_database_and_is_idempotent(tmp_path: Path) -> None:
    assert main(["init", "--root", str(tmp_path)]) == 0
    assert project_database_path(tmp_path).is_file()
    storage = open_db(tmp_path)
    storage.save(Service(storage, Actor.AGENT).create_item(ItemType.EPIC, "Keep me"))
    storage.close()

    assert main(["init", "--root", str(tmp_path)]) == 0  # Does not wipe anything.
    storage = open_db(tmp_path)
    try:
        assert [i.title for i in storage.all()] == ["Keep me"]
    finally:
        storage.close()


def test_init_suggests_import_when_markdown_items_exist(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    legacy_workspace(tmp_path)
    assert main(["init", "--root", str(tmp_path)]) == 0
    assert "specheap import" in capsys.readouterr().out


def test_serve_starts_uvicorn_on_loopback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import uvicorn

    calls: list[dict[str, object]] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))
    main(["init", "--root", str(tmp_path)])

    assert main(["serve", "--root", str(tmp_path), "--port", "9999"]) == 0
    assert calls[0]["host"] == "127.0.0.1" and calls[0]["port"] == 9999
    assert "without authentication" not in capsys.readouterr().err


def test_serve_warns_when_exposed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: None)
    main(["init", "--root", str(tmp_path)])
    main(["serve", "--root", str(tmp_path), "--host", "0.0.0.0"])
    assert "without authentication" in capsys.readouterr().err


def test_approve_flow_and_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["init", "--root", str(tmp_path)])
    storage = open_db(tmp_path)
    agent = Service(storage, Actor.AGENT)
    epic = agent.create_item(ItemType.EPIC, "Auth")

    assert main(["approve", epic.id, "--root", str(tmp_path)]) == 1
    assert "INVALID_TRANSITION" in capsys.readouterr().err  # still a draft

    agent.propose_item(epic.id)
    assert main(["approve", epic.id, "--root", str(tmp_path)]) == 0
    assert agent.get_item(epic.id).status is Status.APPROVED
    storage.close()

    assert main(["approve", "EPIC-099", "--root", str(tmp_path)]) == 1
    assert "NOT_FOUND" in capsys.readouterr().err


def test_gaps_output_and_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["init", "--root", str(tmp_path)])
    assert main(["gaps", "--root", str(tmp_path)]) == 0
    storage = open_db(tmp_path)
    service = Service(storage, Actor.HUMAN)
    epic = service.create_item(ItemType.EPIC, "E")
    feat = service.create_item(ItemType.FEATURE, "F", parent_id=epic.id)
    service.create_item(ItemType.REQ, "R", parent_id=feat.id)
    storage.close()
    capsys.readouterr()
    assert main(["gaps", "--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "reqs without spec: REQ-001" in out and "2 gap(s)." in out


# --------------------------------------------------------------- import/export


def test_import_moves_a_markdown_workspace_into_the_database(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = legacy_workspace(tmp_path)
    expected, expected_log = source.all(), source.log_entries()

    assert main(["import", "--root", str(tmp_path)]) == 0
    assert f"Imported {len(expected)} items" in capsys.readouterr().out

    storage = open_db(tmp_path)
    try:
        assert storage.all() == expected
        log = storage.log_entries()
        assert log[: len(expected_log)] == expected_log
        assert log[-1]["action"] == "import" and log[-1]["actor"] == "system"
    finally:
        storage.close()
    assert source.has_items()  # The markdown files are left untouched.


def test_import_refuses_a_non_empty_database_unless_replacing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    legacy_workspace(tmp_path)
    assert main(["import", "--root", str(tmp_path)]) == 0
    capsys.readouterr()

    assert main(["import", "--root", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "STORAGE_ERROR" in err and "--replace" in err

    assert main(["import", "--root", str(tmp_path), "--replace"]) == 0
    storage = open_db(tmp_path)
    try:
        assert len(storage.all()) == 5  # Replaced, not doubled.
    finally:
        storage.close()


def test_import_without_markdown_items_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["import", "--root", str(tmp_path)]) == 2
    assert "no markdown workspace" in capsys.readouterr().err


def test_a_corrupt_markdown_file_aborts_the_import_without_changes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = legacy_workspace(tmp_path)
    (source.data_dir / "reqs" / "REQ-099.md").write_text("no frontmatter", encoding="utf-8")

    assert main(["import", "--root", str(tmp_path)]) == 1
    assert "VALIDATION_ERROR" in capsys.readouterr().err
    storage = open_db(tmp_path)
    try:
        assert storage.all() == [] and storage.log_entries() == []
    finally:
        storage.close()


def test_export_writes_markdown_and_roundtrips(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    legacy_workspace(tmp_path)
    main(["import", "--root", str(tmp_path)])
    storage = open_db(tmp_path)
    items, log = storage.all(), storage.log_entries()
    storage.close()
    capsys.readouterr()

    out = tmp_path / "copy"
    assert main(["export", "--root", str(tmp_path), "--out", str(out)]) == 0
    assert "snapshot" in capsys.readouterr().out
    exported = FileSystemStorage(out)
    assert exported.all() == items and exported.log_entries() == log

    # Exporting again overwrites instead of duplicating the audit log.
    assert main(["export", "--root", str(tmp_path), "--out", str(out)]) == 0
    assert exported.log_entries() == log


def test_export_refuses_to_write_over_the_workspace(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["init", "--root", str(tmp_path)])
    assert main(["export", "--root", str(tmp_path), "--out", str(tmp_path)]) == 2
    assert "different directory" in capsys.readouterr().err
