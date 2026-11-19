"""Command line interface.

Humans use it to initialize a workspace, approve items and inspect gaps; ``specheap mcp``
starts the MCP server for AI agents and ``specheap serve`` the web UI. Workspaces live in a
SQLite database at ``<project>/.specheap/specheap.db``.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from specheap import __version__
from specheap.core.errors import SpecHeapError
from specheap.core.models import Actor
from specheap.core.ports import Storage
from specheap.core.service import Service
from specheap.storage import FileSystemStorage, SQLiteStorage, project_database_path
from specheap.storage.migrate import export_workspace, import_workspace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="specheap", description="Spec-Driven Development workspace."
    )
    parser.add_argument("--version", action="version", version=f"specheap {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_root(p: argparse.ArgumentParser) -> None:
        p.add_argument("--root", default=".", help="Project root (default: current directory).")

    add_root(sub.add_parser("init", help="Create the workspace database (.specheap/specheap.db)."))

    mcp = sub.add_parser("mcp", help="Run the MCP server over stdio.")
    add_root(mcp)
    mcp.add_argument("--readonly", action="store_true", help="Expose read tools only.")

    serve = sub.add_parser("serve", help="Run the local web UI.")
    add_root(serve)
    serve.add_argument("--host", default="127.0.0.1", help="Interface to bind (default: loopback).")
    serve.add_argument("--port", type=int, default=8765, help="Port (default: 8765).")
    serve.add_argument(
        "--allowed-host",
        action="append",
        default=[],
        help="Extra Host header value to accept (repeatable). Needed when exposing the UI.",
    )

    approve = sub.add_parser("approve", help="Approve a proposed item (humans only).")
    add_root(approve)
    approve.add_argument("item_id", help="Item id, e.g. REQ-012.")

    gaps = sub.add_parser("gaps", help="List traceability gaps.")
    add_root(gaps)
    gaps.add_argument("--scope", default=None, help="Limit to an item and its dependents.")

    import_cmd = sub.add_parser(
        "import", help="Import an old markdown workspace (.specheap/*/*.md) into the database."
    )
    add_root(import_cmd)
    import_cmd.add_argument(
        "--replace", action="store_true", help="Overwrite a database that already has items."
    )

    export = sub.add_parser("export", help="Write a markdown copy of the workspace.")
    add_root(export)
    export.add_argument(
        "--out", default="specheap-export", help="Directory to write to (default: specheap-export)."
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root)
    try:
        if args.command == "init":
            return _init(root)
        if args.command == "import":
            return _import(root, replace=args.replace)

        database = project_database_path(root)
        if not database.is_file():
            return _missing_workspace(root)
        storage = SQLiteStorage(database)
        try:
            return _run(args, storage)
        finally:
            storage.close()
    except SpecHeapError as error:
        hint = f"\nhint: {error.hint}" if error.hint else ""
        print(f"error [{error.code}]: {error.message}{hint}", file=sys.stderr)
        return 1


def _run(args: argparse.Namespace, storage: SQLiteStorage) -> int:
    if args.command == "mcp":
        from specheap.mcp import build_server

        service = Service(storage, Actor.AGENT, readonly=args.readonly)
        build_server(service).run(transport="stdio")
        return 0
    if args.command == "serve":
        return _serve(storage, args)
    if args.command == "export":
        return _export(storage, Path(args.root), Path(args.out))
    service = Service(storage, Actor.HUMAN)
    if args.command == "approve":
        item = service.approve_item(args.item_id)
        print(f"{item.id} approved.")
        return 0
    if args.command == "gaps":
        return _print_gaps(service, args.scope)
    return 2


def _missing_workspace(root: Path) -> int:
    if FileSystemStorage(root).has_items():
        print(
            f"error: {root.resolve()} uses the old markdown format. "
            "Run 'specheap import' to move it to the database.",
            file=sys.stderr,
        )
    else:
        print(
            f"error: no workspace in {root.resolve()}. Run 'specheap init' first.", file=sys.stderr
        )
    return 2


def _init(root: Path) -> int:
    storage = SQLiteStorage.for_project(root)
    storage.close()
    print(f"Initialized {project_database_path(root)}")
    if FileSystemStorage(root).has_items():
        print("Found markdown items from an older version: run 'specheap import' to load them.")
    return 0


def _import(root: Path, *, replace: bool) -> int:
    source = FileSystemStorage(root)
    if not source.has_items():
        print(f"error: no markdown workspace found in {root.resolve()}.", file=sys.stderr)
        return 2
    target = SQLiteStorage.for_project(root)
    try:
        result = import_workspace(source, target, replace=replace)
    finally:
        target.close()
    print(
        f"Imported {result.items} items and {result.log_entries} audit entries into "
        f"{project_database_path(root)}."
    )
    print("The markdown files were left untouched; delete them once you have checked the data.")
    return 0


def _export(storage: Storage, root: Path, out: Path) -> int:
    destination = FileSystemStorage(out)
    if destination.data_dir.resolve() == project_database_path(root).parent.resolve():
        print(
            "error: --out must be a different directory than the workspace itself.",
            file=sys.stderr,
        )
        return 2
    result = export_workspace(storage, destination)
    print(
        f"Exported {result.items} items and {result.log_entries} audit entries to "
        f"{destination.data_dir}. This is a snapshot: the database remains the source of truth."
    )
    return 0


_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def _serve(storage: Storage, args: argparse.Namespace) -> int:
    import uvicorn

    from specheap.web import DEFAULT_ALLOWED_HOSTS, create_app, frontend_built

    if not frontend_built():
        print(
            "warning: the frontend is not built; only the API is available. "
            "Run 'npm install && npm run build' in frontend/.",
            file=sys.stderr,
        )
    allowed = [*DEFAULT_ALLOWED_HOSTS, args.host, *args.allowed_host]
    if args.host not in _LOOPBACK_HOSTS:
        print(
            f"warning: binding to {args.host} exposes the UI, including approval, to the network "
            "without authentication.",
            file=sys.stderr,
        )
    app = create_app(storage, allowed_hosts=sorted(set(allowed)))
    print(f"SpecHeap UI running at http://{args.host}:{args.port} (Ctrl+C to stop)")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def _print_gaps(service: Service, scope: str | None) -> int:
    gaps = service.list_gaps(scope)
    for name, ids in gaps.model_dump().items():
        if ids:
            print(f"{name.replace('_', ' ')}: {', '.join(ids)}")
    print(f"{gaps.total} gap(s).")
    return 0 if gaps.total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
