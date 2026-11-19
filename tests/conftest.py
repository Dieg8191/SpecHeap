"""Shared fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from specheap.core.models import Actor
from specheap.core.ports import Storage
from specheap.core.service import Service
from specheap.storage import FileSystemStorage, MemoryStorage


@pytest.fixture(params=["memory", "fs"])
def storage(request: pytest.FixtureRequest, tmp_path: Path) -> Storage:
    """Run every storage-dependent test against both adapters."""
    if request.param == "memory":
        return MemoryStorage()
    return FileSystemStorage(tmp_path)


@pytest.fixture
def human(storage: Storage) -> Service:
    return Service(storage, Actor.HUMAN)


@pytest.fixture
def agent(storage: Storage) -> Service:
    return Service(storage, Actor.AGENT)
