"""SQLite storage: the default and only source of truth of a workspace.

The database lives at ``<project>/.specheap/specheap.db`` and uses the standard library
``sqlite3`` module. Design notes:

* **Write-ahead logging** lets the MCP server, the web UI and the CLI read while one of them
  writes, each from its own process.
* **Transactions** start with ``BEGIN IMMEDIATE``: writers take the database write lock up
  front and wait for each other (up to ``BUSY_TIMEOUT_SECONDS``). Together with reading the
  next identifier inside the same transaction, that is what makes identifiers unique and
  multi-step operations atomic.
* **One connection per thread**: a connection is only ever used by the thread that opened it.
* **Schema versions** are stored in ``PRAGMA user_version``. Opening a database created by a
  newer SpecHeap fails with a clear error; older ones are upgraded by ``_MIGRATIONS``.

Parents and links are not foreign keys on purpose: the service layer validates them, and
imports of hand-edited data must not be rejected by the database.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from specheap.core.errors import StorageError
from specheap.core.ids import parse_id
from specheap.core.models import Item, ItemType

DATABASE_NAME = "specheap.db"
DATA_DIR_NAME = ".specheap"
SCHEMA_VERSION = 1
BUSY_TIMEOUT_SECONDS = 15.0

# Statements that upgrade a database to each version. Executed one by one (not with
# ``executescript``, which would commit the surrounding transaction).
_MIGRATIONS: dict[int, tuple[str, ...]] = {
    1: (
        """
        CREATE TABLE items (
            id       TEXT PRIMARY KEY,
            type     TEXT NOT NULL,
            number   INTEGER NOT NULL,
            title    TEXT NOT NULL,
            status   TEXT NOT NULL,
            parent   TEXT,
            body     TEXT NOT NULL DEFAULT '',
            result   TEXT,
            evidence TEXT NOT NULL DEFAULT '',
            run_ref  TEXT,
            UNIQUE (type, number)
        )
        """,
        "CREATE INDEX items_parent ON items (parent)",
        """
        CREATE TABLE links (
            source   TEXT NOT NULL REFERENCES items (id) ON DELETE CASCADE,
            relation TEXT NOT NULL CHECK (relation IN ('satisfies', 'verifies')),
            target   TEXT NOT NULL,
            position INTEGER NOT NULL,
            PRIMARY KEY (source, relation, target)
        )
        """,
        """
        CREATE TABLE audit_log (
            seq     INTEGER PRIMARY KEY AUTOINCREMENT,
            ts      TEXT NOT NULL,
            actor   TEXT NOT NULL,
            action  TEXT NOT NULL,
            item_id TEXT,
            data    TEXT NOT NULL
        )
        """,
        "CREATE INDEX audit_log_item ON audit_log (item_id)",
    ),
}

_UPSERT_ITEM = """
INSERT INTO items (id, type, number, title, status, parent, body, result, evidence, run_ref)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (id) DO UPDATE SET
    title = excluded.title, status = excluded.status, parent = excluded.parent,
    body = excluded.body, result = excluded.result, evidence = excluded.evidence,
    run_ref = excluded.run_ref
"""


def project_database_path(root: str | Path) -> Path:
    """Location of the workspace database for a project root."""
    return Path(root) / DATA_DIR_NAME / DATABASE_NAME


class SQLiteStorage:
    """Persists items, links and the audit log in a single SQLite database."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._local = threading.local()
        self._connections: list[sqlite3.Connection] = []
        self._registry_lock = threading.Lock()
        self._conn()  # Fail early (and create the schema) rather than on first use.

    @classmethod
    def for_project(cls, root: str | Path) -> SQLiteStorage:
        """Open (creating if needed) the database of the project at ``root``."""
        return cls(project_database_path(root))

    # ------------------------------------------------------------ connections

    def _conn(self) -> sqlite3.Connection:
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._open()
            self._local.conn = conn
            with self._registry_lock:
                self._connections.append(conn)
        return conn

    def _open(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Autocommit mode: transactions are explicit. ``check_same_thread`` is off only so
            # that ``close()`` can release every connection; each is used by one thread.
            conn = sqlite3.connect(
                self.path,
                timeout=BUSY_TIMEOUT_SECONDS,
                isolation_level=None,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA journal_mode = WAL")
            _migrate(conn)
        except sqlite3.Error as error:
            raise StorageError(
                f"Cannot open the database {self.path}: {error}",
                hint="Check that the file is a SpecHeap database and is not locked or read-only.",
                path=str(self.path),
            ) from error
        return conn

    def close(self) -> None:
        """Close every connection. The storage reopens lazily if used again."""
        with self._registry_lock:
            for conn in self._connections:
                conn.close()
            self._connections.clear()
        self._local = threading.local()

    # ----------------------------------------------------------- transactions

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Run the block as one atomic unit; see ``Storage.transaction``."""
        conn = self._conn()
        depth: int = getattr(self._local, "depth", 0)
        if depth > 0:
            self._local.depth = depth + 1
            try:
                yield
            finally:
                self._local.depth -= 1
            return
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as error:
            raise StorageError(
                f"Could not obtain the database write lock: {error}",
                hint="Another SpecHeap process may be holding it; try again.",
            ) from error
        self._local.depth = 1
        try:
            yield
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")
        finally:
            self._local.depth = 0

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        """A consistent snapshot for reads that span several statements."""
        conn = self._conn()
        if getattr(self._local, "depth", 0) > 0:
            yield conn
            return
        conn.execute("BEGIN")
        try:
            yield conn
        finally:
            conn.execute("COMMIT")

    # ------------------------------------------------------------------ items

    def get(self, item_id: str) -> Item | None:
        with self._read() as conn:
            row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
            if row is None:
                return None
            links = conn.execute(
                "SELECT relation, target FROM links WHERE source = ? ORDER BY position", (item_id,)
            ).fetchall()
        return _to_item(row, _group_links(links))

    def all(self) -> list[Item]:
        with self._read() as conn:
            rows = conn.execute("SELECT * FROM items ORDER BY type, number").fetchall()
            links = conn.execute(
                "SELECT source, relation, target FROM links ORDER BY source, position"
            ).fetchall()
        by_source: dict[str, dict[str, list[str]]] = {}
        for link in links:
            by_source.setdefault(link["source"], {}).setdefault(link["relation"], []).append(
                link["target"]
            )
        return [_to_item(row, by_source.get(row["id"], {})) for row in rows]

    def save(self, item: Item) -> None:
        _, number = parse_id(item.id)
        with self.transaction():
            conn = self._conn()
            conn.execute(
                _UPSERT_ITEM,
                (
                    item.id,
                    item.type.value,
                    number,
                    item.title,
                    item.status.value,
                    item.parent,
                    item.body,
                    item.result.value if item.result else None,
                    item.evidence,
                    item.run_ref,
                ),
            )
            conn.execute("DELETE FROM links WHERE source = ?", (item.id,))
            rows = [
                (item.id, relation, target, position)
                for relation, targets in (
                    ("satisfies", item.satisfies),
                    ("verifies", item.verifies),
                )
                for position, target in enumerate(dict.fromkeys(targets))
            ]
            conn.executemany(
                "INSERT INTO links (source, relation, target, position) VALUES (?, ?, ?, ?)", rows
            )

    def next_number(self, item_type: ItemType) -> int:
        with self._read() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(number), 0) + 1 FROM items WHERE type = ?", (item_type.value,)
            ).fetchone()
        return int(row[0])

    def clear(self) -> None:
        """Delete every item, link and audit entry (used by ``import --replace``)."""
        with self.transaction():
            conn = self._conn()
            conn.execute("DELETE FROM links")
            conn.execute("DELETE FROM items")
            conn.execute("DELETE FROM audit_log")

    # -------------------------------------------------------------- audit log

    def append_log(self, entry: dict[str, Any]) -> None:
        with self.transaction():
            self._conn().execute(
                "INSERT INTO audit_log (ts, actor, action, item_id, data) VALUES (?, ?, ?, ?, ?)",
                (
                    str(entry.get("ts", "")),
                    str(entry.get("actor", "")),
                    str(entry.get("action", "")),
                    entry.get("id"),
                    json.dumps(entry, ensure_ascii=False, sort_keys=True),
                ),
            )

    def log_entries(self) -> list[dict[str, Any]]:
        with self._read() as conn:
            rows = conn.execute("SELECT data FROM audit_log ORDER BY seq").fetchall()
        return [json.loads(row["data"]) for row in rows]


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring the database to ``SCHEMA_VERSION`` (creating it when new)."""
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if version > SCHEMA_VERSION:
        raise StorageError(
            f"The database uses schema version {version}, but this SpecHeap supports up to "
            f"{SCHEMA_VERSION}.",
            hint="Upgrade SpecHeap to open this workspace.",
        )
    if version == SCHEMA_VERSION:
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Re-read under the lock: another process may have migrated in the meantime.
        current = int(conn.execute("PRAGMA user_version").fetchone()[0])
        for target in range(current + 1, SCHEMA_VERSION + 1):
            for statement in _MIGRATIONS[target]:
                conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {target}")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def _group_links(rows: list[sqlite3.Row]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for row in rows:
        grouped.setdefault(row["relation"], []).append(row["target"])
    return grouped


def _to_item(row: sqlite3.Row, links: dict[str, list[str]]) -> Item:
    return Item.model_validate(
        {
            "id": row["id"],
            "type": row["type"],
            "title": row["title"],
            "status": row["status"],
            "parent": row["parent"],
            "body": row["body"],
            "result": row["result"],
            "evidence": row["evidence"],
            "run_ref": row["run_ref"],
            "satisfies": links.get("satisfies", []),
            "verifies": links.get("verifies", []),
        }
    )
