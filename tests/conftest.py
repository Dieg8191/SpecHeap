"""Shared fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from specheap.core.models import Actor
from specheap.core.ports import Storage
from specheap.core.service import Service
from specheap.storage import MemoryStorage, SQLiteStorage


@pytest.fixture(params=["memory", "sqlite"])
def storage(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Storage]:
    """Run every storage-dependent test against every adapter."""
    if request.param == "memory":
        yield MemoryStorage()
    else:
        sqlite = SQLiteStorage(tmp_path / "specheap.db")
        yield sqlite
        sqlite.close()


@pytest.fixture
def human(storage: Storage) -> Service:
    return Service(storage, Actor.HUMAN)


@pytest.fixture
def agent(storage: Storage) -> Service:
    return Service(storage, Actor.AGENT)
