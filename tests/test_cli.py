"""Tests for the command line interface."""

from __future__ import annotations

from pathlib import Path

import pytest

from specheap.cli import main
from specheap.core.models import Actor, ItemType, Status
from specheap.core.service import Service
from specheap.storage import FileSystemStorage


def test_commands_require_init(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["gaps", "--root", str(tmp_path)]) == 2
    assert "specheap init" in capsys.readouterr().err


def test_init_creates_layout(tmp_path: Path) -> None:
    assert main(["init", "--root", str(tmp_path)]) == 0
    assert (tmp_path / ".specheap" / "reqs").is_dir()


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
    storage = FileSystemStorage(tmp_path)
    agent = Service(storage, Actor.AGENT)
    epic = agent.create_item(ItemType.EPIC, "Auth")

    assert main(["approve", epic.id, "--root", str(tmp_path)]) == 1
    assert "INVALID_TRANSITION" in capsys.readouterr().err  # still a draft

    agent.propose_item(epic.id)
    assert main(["approve", epic.id, "--root", str(tmp_path)]) == 0
    assert agent.get_item(epic.id).status is Status.APPROVED

    assert main(["approve", "EPIC-099", "--root", str(tmp_path)]) == 1
    assert "NOT_FOUND" in capsys.readouterr().err


def test_gaps_output_and_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["init", "--root", str(tmp_path)])
    assert main(["gaps", "--root", str(tmp_path)]) == 0
    service = Service(FileSystemStorage(tmp_path), Actor.HUMAN)
    epic = service.create_item(ItemType.EPIC, "E")
    feat = service.create_item(ItemType.FEATURE, "F", parent_id=epic.id)
    service.create_item(ItemType.REQ, "R", parent_id=feat.id)
    capsys.readouterr()
    assert main(["gaps", "--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "reqs without spec: REQ-001" in out and "2 gap(s)." in out
