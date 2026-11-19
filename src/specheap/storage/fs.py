"""Filesystem storage: one markdown file per item, with YAML frontmatter.

This is the original storage format. SQLite is now the default and only source of truth;
this adapter remains as the engine behind ``specheap import`` (reading old workspaces) and
``specheap export`` (writing a human-readable copy). It is not atomic: ``transaction()`` is a
no-op, so do not use it to serve concurrent writers.

Layout (relative to the project root)::

    .specheap/
      epics/EPIC-001.md
      features/FEAT-001.md
      reqs/REQ-001.md
      specs/SPEC-001.md
      verifications/VER-001.md
      log.jsonl

Output is deterministic and human-readable.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from specheap.core.errors import ValidationFailedError
from specheap.core.ids import parse_id
from specheap.core.models import Item, ItemType
from specheap.storage.memory import next_number

DATA_DIR_NAME = ".specheap"

_DIRECTORIES: dict[ItemType, str] = {
    ItemType.EPIC: "epics",
    ItemType.FEATURE: "features",
    ItemType.REQ: "reqs",
    ItemType.SPEC: "specs",
    ItemType.VERIFICATION: "verifications",
}

_FILE_PATTERN = re.compile(r"\A---\n(?P<meta>.*?)^---\n(?P<body>.*)\Z", re.DOTALL | re.MULTILINE)


class FileSystemStorage:
    """Persists items as markdown files under ``<root>/.specheap``."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.data_dir = self.root / DATA_DIR_NAME

    def init(self) -> None:
        """Create the data directory layout. Safe to call repeatedly."""
        for directory in _DIRECTORIES.values():
            (self.data_dir / directory).mkdir(parents=True, exist_ok=True)

    def get(self, item_id: str) -> Item | None:
        item_type, _ = parse_id(item_id)
        path = self._path(item_type, item_id)
        if not path.is_file():
            return None
        return _read_item(path)

    def save(self, item: Item) -> None:
        path = self._path(item.type, item.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, _render_item(item))

    def all(self) -> list[Item]:
        items: list[Item] = []
        for directory in _DIRECTORIES.values():
            folder = self.data_dir / directory
            if folder.is_dir():
                items.extend(_read_item(path) for path in sorted(folder.glob("*.md")))
        return items

    def next_number(self, item_type: ItemType) -> int:
        return next_number(self.all(), item_type)

    def append_log(self, entry: dict[str, Any]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        with (self.data_dir / "log.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")

    def log_entries(self) -> list[dict[str, Any]]:
        path = self.data_dir / "log.jsonl"
        if not path.is_file():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """No-op: files cannot be updated atomically, so writes are applied one by one."""
        yield

    def _path(self, item_type: ItemType, item_id: str) -> Path:
        return self.data_dir / _DIRECTORIES[item_type] / f"{item_id}.md"


def _render_item(item: Item) -> str:
    meta = item.model_dump(mode="json", exclude={"body"}, exclude_defaults=False)
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return f"---\n{front}---\n{item.body}"


def _read_item(path: Path) -> Item:
    text = path.read_text(encoding="utf-8")
    match = _FILE_PATTERN.match(text)
    if match is None:
        raise ValidationFailedError(
            f"Item file has no valid frontmatter: {path}.",
            hint="Files must start with a '---' delimited YAML block.",
            path=str(path),
        )
    try:
        meta = yaml.safe_load(match.group("meta")) or {}
        return Item.model_validate({**meta, "body": match.group("body")})
    except (yaml.YAMLError, ValidationError) as error:
        raise ValidationFailedError(
            f"Item file is invalid: {path}.",
            hint=str(error).splitlines()[0],
            path=str(path),
        ) from error


def _atomic_write(path: Path, content: str) -> None:
    """Write via a temp file and rename so readers never see partial content."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    os.replace(tmp, path)
