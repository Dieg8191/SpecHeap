"""Move a workspace between the markdown format and SQLite.

``import_workspace`` upgrades an old markdown workspace to the database. ``export_workspace``
writes a human-readable markdown copy of the database (a snapshot: edits made to the exported
files are not read back unless you import them again).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from specheap.core.errors import StorageError
from specheap.core.ids import parse_id
from specheap.core.models import Item, ItemType
from specheap.core.ports import Storage
from specheap.storage.fs import FileSystemStorage
from specheap.storage.sqlite import SQLiteStorage

_TYPE_ORDER = list(ItemType)


@dataclass(frozen=True)
class TransferResult:
    """How much data was moved."""

    items: int
    log_entries: int


def _ordered(items: list[Item]) -> list[Item]:
    return sorted(items, key=lambda i: (_TYPE_ORDER.index(i.type), parse_id(i.id)[1]))


def import_workspace(
    source: FileSystemStorage, target: SQLiteStorage, *, replace: bool = False
) -> TransferResult:
    """Copy every item and audit entry from a markdown workspace into the database.

    The source is read completely before the database is touched, so a corrupt file aborts the
    import without changing anything, and the copy itself is a single transaction.

    Raises:
        StorageError: if the database already has items and ``replace`` is false.
        ValidationFailedError: if a markdown file is invalid (the message names the file).
    """
    items = _ordered(source.all())
    log = source.log_entries()
    with target.transaction():
        existing = len(target.all())
        if existing and not replace:
            raise StorageError(
                f"The database already contains {existing} items.",
                hint="Use --replace to overwrite it with the contents of the markdown workspace.",
                existing_items=existing,
            )
        if replace:
            target.clear()
        for item in items:
            target.save(item)
        for entry in log:
            target.append_log(entry)
        target.append_log(
            {
                "ts": datetime.now(UTC).isoformat(timespec="seconds"),
                "actor": "system",
                "action": "import",
                "items": len(items),
                "log_entries": len(log),
            }
        )
    return TransferResult(items=len(items), log_entries=len(log))


def export_workspace(source: Storage, target: FileSystemStorage) -> TransferResult:
    """Write every item and the audit log as markdown files under ``target``."""
    items = _ordered(source.all())
    log = source.log_entries()
    target.init()
    for item in items:
        target.save(item)
    target.replace_log(log)
    return TransferResult(items=len(items), log_entries=len(log))
