"""MCP server built on top of ``specheap.core.service.Service``.

This module is a thin adapter: it contains no business rules. Permissions, lifecycle and
concurrency checks all live in the service, which the server always runs as ``Actor.AGENT``.
Approval is deliberately not exposed as a tool.

Errors are returned as tool errors whose message is a JSON object with ``code``, ``message``
and, when available, ``hint`` and ``details`` (see ``SpecHeapError.to_dict``).
"""

import functools
import json
from collections.abc import Callable
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from specheap import __version__
from specheap.core.errors import SpecHeapError, ValidationFailedError
from specheap.core.models import Actor, Item, ItemType, Status, VerificationResult
from specheap.core.schemas import ContextDTO, ItemDTO, TraceDTO, context_dto, to_dtos
from specheap.core.service import Gaps, Overview, Relation, Service

INSTRUCTIONS = """\
SpecHeap stores a Spec-Driven Development graph: Epic > Feature > Requirement > Spec > \
Verification. Start with get_overview or list_gaps, then get_context(id) for the item you \
work on. You can create and edit items and propose them for review, but only a human can \
approve. Editing an approved item sends it back to 'proposed' and marks dependents 'stale'. \
Always pass the latest revision to update_item. Report test outcomes with report_verification."""

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


class ItemList(BaseModel):
    """A page of items."""

    items: list[ItemDTO]
    total: int
    next_cursor: str | None = None


def _guard(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Translate domain errors into structured MCP tool errors."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except SpecHeapError as error:
            raise ToolError(json.dumps(error.to_dict(), ensure_ascii=False)) from error

    return wrapper


def build_server(service: Service) -> MCPServer:
    """Create the MCP server for ``service``.

    Write tools are only registered when the service is not read-only.

    Raises:
        ValueError: if the service is not bound to the agent actor.
    """
    if service.actor is not Actor.AGENT:
        raise ValueError("The MCP server must run as Actor.AGENT.")

    server = MCPServer("specheap", instructions=INSTRUCTIONS, version=__version__)
    read_only = ToolAnnotations(readOnlyHint=True)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=False)

    def read_tool(fn: Callable[..., Any]) -> Callable[..., Any]:
        return server.tool(annotations=read_only)(_guard(fn))

    def write_tool(fn: Callable[..., Any]) -> Callable[..., Any]:
        return server.tool(annotations=write)(_guard(fn))

    # ------------------------------------------------------------ read tools

    @read_tool
    def get_overview() -> Overview:
        """Counts by type and status, requirement coverage percentage, open gaps and stale items."""
        return service.get_overview()

    @read_tool
    def list_items(
        item_type: ItemType | None = None,
        status: Status | None = None,
        parent_id: str | None = None,
        query: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> ItemList:
        """List items with optional filters. Paginated: pass next_cursor back as cursor."""
        offset = _parse_cursor(cursor)
        size = min(max(limit, 1), MAX_PAGE_SIZE)
        found = service.list_items(
            item_type=item_type, status=status, parent_id=parent_id, query=query
        )
        page = found[offset : offset + size]
        more = offset + size < len(found)
        return ItemList(
            items=to_dtos(page), total=len(found), next_cursor=str(offset + size) if more else None
        )

    @read_tool
    def get_item(item_id: str) -> ItemDTO:
        """Get one item with its current revision (required to edit it)."""
        return ItemDTO.from_item(service.get_item(item_id))

    @read_tool
    def get_context(item_id: str, depth: int | None = None) -> ContextDTO:
        """Best first call when working on an item: its ancestor chain up to the epic plus all
        descendants (requirements, specs, verifications) with their status.
        depth limits descendant levels."""
        return context_dto(service.get_context(item_id, depth))

    @read_tool
    def trace(item_id: str, direction: Literal["up", "down", "both"] = "both") -> TraceDTO:
        """Follow traceability from an item up to its epic and/or down to its verifications."""
        result = service.trace(item_id, direction)
        return TraceDTO(
            item=ItemDTO.from_item(result.item),
            upstream=to_dtos(result.upstream),
            downstream=to_dtos(result.downstream),
        )

    @read_tool
    def list_gaps(scope_id: str | None = None) -> Gaps:
        """Requirements without specs or verifications, specs without verifications, stale items
        and failed verifications. scope_id limits the report to that item and its dependents."""
        return service.list_gaps(scope_id)

    @read_tool
    def next_work(limit: int = 10) -> ItemList:
        """Approved requirements and specs that are ready to implement."""
        items = service.next_work(limit)
        return ItemList(items=to_dtos(items), total=len(items))

    # ----------------------------------------------------------- write tools

    if not service.readonly:

        @write_tool
        def create_item(
            item_type: ItemType, title: str, parent_id: str | None = None, body: str = ""
        ) -> ItemDTO:
            """Create an item in 'draft'. Parent types: feature>epic, req>feature, spec>req,
            verification>req or spec. Epics have no parent."""
            return ItemDTO.from_item(
                service.create_item(item_type, title, parent_id=parent_id, body=body)
            )

        @write_tool
        def update_item(
            item_id: str,
            expected_revision: str,
            title: str | None = None,
            body: str | None = None,
        ) -> ItemDTO:
            """Edit title and/or body. expected_revision must be the revision from your last
            read, otherwise REVISION_CONFLICT is returned. Editing an approved item resets it
            to 'proposed' and marks dependents 'stale'."""
            patch = {k: v for k, v in {"title": title, "body": body}.items() if v is not None}
            if not patch:
                raise ValidationFailedError(
                    "Nothing to update.", hint="Provide title and/or body.", field="title"
                )
            return ItemDTO.from_item(service.update_item(item_id, patch, expected_revision))

        @write_tool
        def propose_item(item_id: str) -> ItemDTO:
            """Move a draft item to 'proposed' to request human review. Agents cannot approve."""
            return ItemDTO.from_item(service.propose_item(item_id))

        @write_tool
        def link_items(from_id: str, to_id: str, relation: Relation) -> ItemDTO:
            """Add a link: 'satisfies' (spec -> additional req) or 'verifies' (verification ->
            req or spec). The parent relationship is implicit and needs no link."""
            return ItemDTO.from_item(service.link_items(from_id, to_id, relation))

        @write_tool
        def unlink_items(from_id: str, to_id: str, relation: Relation) -> ItemDTO:
            """Remove a 'satisfies' or 'verifies' link."""
            return ItemDTO.from_item(service.unlink_items(from_id, to_id, relation))

        @write_tool
        def mark_implemented(item_id: str, evidence: str = "") -> ItemDTO:
            """Mark an approved requirement or spec as implemented (evidence: PR, commit...)."""
            return ItemDTO.from_item(service.mark_implemented(item_id, evidence))

        @write_tool
        def report_verification(
            item_id: str,
            result: VerificationResult,
            evidence: str = "",
            run_ref: str | None = None,
        ) -> ItemDTO:
            """Record a verification outcome (pass, fail or skipped). When all verifications of
            an implemented item pass, the item becomes 'verified' automatically."""
            return ItemDTO.from_item(
                service.report_verification(item_id, result, evidence=evidence, run_ref=run_ref)
            )

    _register_resources(server, service)
    _register_prompts(server)
    return server


def _parse_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    if not cursor.isdigit():
        raise ToolError(
            json.dumps(
                ValidationFailedError(
                    f"Invalid cursor: {cursor!r}.",
                    hint="Pass the next_cursor value returned by the previous page.",
                    field="cursor",
                ).to_dict()
            )
        )
    return int(cursor)


def _item_markdown(item: Item) -> str:
    links = []
    if item.satisfies:
        links.append(f"satisfies: {', '.join(item.satisfies)}")
    if item.verifies:
        links.append(f"verifies: {', '.join(item.verifies)}")
    meta = " | ".join(
        [f"status: {item.status.value}", f"parent: {item.parent or '-'}", *links,
         f"revision: {item.revision}"]
    )
    return f"# {item.id}: {item.title}\n\n{meta}\n\n{item.body}"


# ---------------------------------------------------------------- resources


def _register_resources(server: MCPServer, service: Service) -> None:
    def guarded(fn: Callable[..., str]) -> Callable[..., str]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> str:
            try:
                return fn(*args, **kwargs)
            except SpecHeapError as error:
                raise ResourceError(json.dumps(error.to_dict(), ensure_ascii=False)) from error

        return wrapper

    @server.resource("specheap://overview", mime_type="application/json")
    @guarded
    def overview_resource() -> str:
        """Workspace overview as JSON."""
        return service.get_overview().model_dump_json(indent=2)

    @server.resource("specheap://feature/{item_id}/context", mime_type="application/json")
    @guarded
    def feature_context_resource(item_id: str) -> str:
        """A feature with its ancestors and descendants as JSON (same as get_context)."""
        return context_dto(service.get_context(item_id)).model_dump_json(indent=2)

    @server.resource("specheap://{item_type}/{item_id}", mime_type="text/markdown")
    @guarded
    def item_resource(item_type: str, item_id: str) -> str:
        """An item rendered as markdown."""
        item = service.get_item(item_id)
        if item.type.value != item_type:
            raise ValidationFailedError(
                f"{item_id} is a {item.type.value}, not a {item_type}.",
                hint=f"Use specheap://{item.type.value}/{item_id}.",
            )
        return _item_markdown(item)


# ------------------------------------------------------------------ prompts


def _register_prompts(server: MCPServer) -> None:
    @server.prompt()
    def decompose_feature(feature_id: str) -> str:
        """Break a feature into testable requirements."""
        return (
            f"Call get_context for {feature_id}. Propose requirements that fully cover the "
            "feature. Write each in EARS form ('WHEN <trigger>, the system SHALL <response>'), "
            "one behavior per requirement, no implementation details. Create each with "
            f"create_item(item_type='req', parent_id='{feature_id}') and finish with "
            "propose_item so a human can review them."
        )

    @server.prompt()
    def draft_specs(req_id: str) -> str:
        """Propose technical specs for a requirement."""
        return (
            f"Call get_context for {req_id}. Draft specs describing HOW it will be built: "
            "interfaces, data contracts and key decisions. Create them with "
            f"create_item(item_type='spec', parent_id='{req_id}'), then propose_item each one."
        )

    @server.prompt()
    def plan_verifications(req_id: str) -> str:
        """Propose measurable verifications for a requirement."""
        return (
            f"Call get_context for {req_id}. For every requirement and spec without a "
            "verification, propose one with a concrete, measurable pass criterion (automated "
            "test name or exact manual steps). Create them with "
            "create_item(item_type='verification', parent_id=<req or spec id>)."
        )

    @server.prompt()
    def review_gaps() -> str:
        """Walk through traceability gaps and propose how to close them."""
        return (
            "Call list_gaps. For each gap explain why it matters and propose the smallest change "
            "that closes it (missing spec, missing verification, stale item to revise, failing "
            "verification to fix). Do not change anything until the user agrees."
        )
