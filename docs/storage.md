# Storage

SpecHeap keeps a workspace in one SQLite database: `<project>/.specheap/specheap.db`. It is the
only source of truth. This document explains the design and the guarantees callers can rely on.

## Why SQLite

The first versions stored one markdown file per item. That is easy to read but cannot give
atomic multi-item updates, safe identifier allocation across processes, or fast graph queries.
SQLite gives all three with no server, ships with Python, and fits the local-first goal. Git
based review of specs was deliberately dropped in favor of these guarantees; a versioning model
is planned instead (see below).

## Schema (version 1)

| Table | Purpose |
|---|---|
| `items` | One row per item: `id`, `type`, `number`, `title`, `status`, `parent`, `body`, and for verifications `result`, `evidence`, `run_ref`. `UNIQUE (type, number)`. |
| `links` | `satisfies` and `verifies` links stored on the child side: `source`, `relation`, `target`, `position` (keeps the order). |
| `audit_log` | Append-only: `seq`, `ts`, `actor`, `action`, `item_id` and the full entry as JSON in `data`. |

`parent` and link targets are intentionally **not** foreign keys: the service layer validates
them, and importing hand-edited data must not be rejected by the database. A link row is deleted
with its source item (`ON DELETE CASCADE`).

The revision of an item (used for optimistic concurrency) is a hash computed by the model from
the item's content; it is not stored.

## Transactions and concurrency

- The database runs in **WAL mode**: readers never block the writer and the writer never blocks
  readers, so the MCP server, the web UI and the CLI can use the same file at once.
- `Storage.transaction()` opens `BEGIN IMMEDIATE`. Writers take the write lock up front and wait
  for each other (up to 15 seconds), so there are no lock upgrades or deadlocks.
- Every write operation of `Service` runs in one transaction. Inside it the service reads the
  current state, checks the revision, allocates the identifier (`MAX(number) + 1` for the type)
  and performs every resulting write, including stale propagation, derived `verified` status and
  audit entries. An exception anywhere rolls all of it back.
- Transactions are re-entrant: a nested `transaction()` joins the outer one.
- Each thread uses its own connection, so the MCP server (which may run tools on worker threads)
  and the web server are safe.
- Read-only services never open a transaction, so they never take the write lock.

Guarantees, each covered by tests (`tests/test_atomicity.py`, `tests/test_sqlite.py`):

1. A failure halfway through an operation leaves no partial changes and no audit entries.
2. Concurrent creators, in threads or in separate processes, receive unique sequential ids.
3. When several writers edit an item with the same revision, exactly one succeeds and the rest
   get `REVISION_CONFLICT`.

## Schema versions and migrations

The version lives in `PRAGMA user_version`. On open:

- a database from a **newer** SpecHeap is refused with a clear error asking to upgrade;
- an **older** database is upgraded in place by running the statements in `_MIGRATIONS` for each
  missing version, inside one transaction (another process migrating at the same time is
  handled by re-reading the version under the lock).

To change the schema, add a new entry to `_MIGRATIONS`, bump `SCHEMA_VERSION` and add a test that
opens a database created with the previous version.

## Import and export

- `specheap import` reads an old markdown workspace and copies it into the database in a single
  transaction, together with its audit log, and records an `import` entry. The source is parsed
  completely first, so a corrupt file aborts the import without changing the database. It refuses
  to run on a database that already has items unless `--replace` is given. The markdown files are
  never modified.
- `specheap export --out DIR` writes a markdown copy (one file per item plus `log.jsonl`). The
  output is deterministic: importing and exporting a workspace reproduces the original files
  byte for byte. It is a snapshot; edits made to the exported files are not read back unless you
  import them.

The markdown adapter (`storage/fs.py`) now exists only for these two commands. It is not atomic
and should not serve live traffic.

## Backups

The database file can be copied while no process is writing. To take a consistent copy while
SpecHeap is running, use `specheap export` or SQLite's online backup (`sqlite3 specheap.db
".backup copy.db"`). Besides `specheap.db`, WAL mode creates `specheap.db-wal` and
`specheap.db-shm` next to it while the database is open; they belong to the same database.

## Planned: item history

The audit log already says who changed what and when, and every item has a revision. A future
history feature can add an `item_versions` table written inside the same transaction as each
change (item id, revision, full content, actor, timestamp). That enables diffs and restoring
earlier versions without changing the rest of the schema; it would be added as migration 2.
