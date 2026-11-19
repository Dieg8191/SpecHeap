"""Application service: the single entry point every interface goes through.

``Service`` enforces the business rules (permissions per actor, lifecycle, optimistic
concurrency, stale propagation, derived ``verified`` status and auditing). The MCP server,
CLI and web UI are thin layers on top of it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from specheap.core.errors import (
    NotFoundError,
    ReadonlyModeError,
    RevisionConflictError,
    ValidationFailedError,
)
from specheap.core.graph import Graph
from specheap.core.ids import format_id, parse_id
from specheap.core.lifecycle import check_transition, status_after_edit
from specheap.core.models import (
    Actor,
    Item,
    ItemType,
    Status,
    VerificationResult,
    validate_parent,
)
from specheap.core.ports import Storage

Relation = Literal["satisfies", "verifies"]

# Fields a caller may change through ``update_item``. Everything else is managed by the core.
EDITABLE_FIELDS = frozenset({"title", "body"})

# Statuses whose content was already reviewed; editing them invalidates dependents.
_REVIEWED = frozenset({Status.APPROVED, Status.IMPLEMENTED, Status.VERIFIED})
# Statuses that become ``stale`` when something upstream changes.
_STALEABLE = frozenset({Status.PROPOSED, Status.APPROVED, Status.IMPLEMENTED, Status.VERIFIED})

_TYPE_ORDER = list(ItemType)


class Gaps(BaseModel):
    """Traceability problems found in the graph."""

    reqs_without_spec: list[str] = []
    reqs_without_verification: list[str] = []
    specs_without_verification: list[str] = []
    stale: list[str] = []
    failed_verifications: list[str] = []

    @property
    def total(self) -> int:
        return sum(len(v) for v in self.model_dump().values())


class Overview(BaseModel):
    """High-level health of the workspace."""

    total_items: int
    by_type: dict[str, int]
    by_status: dict[str, int]
    coverage_percent: float
    """Share of requirements that have at least one spec and one verification."""
    gaps: int
    stale: int


class Context(BaseModel):
    """Everything an agent needs to work on one item."""

    item: Item
    ancestors: list[Item]
    descendants: list[Item]


class Trace(BaseModel):
    """Traceability chains around one item."""

    item: Item
    upstream: list[Item] = []
    downstream: list[Item] = []


class Service:
    """Business operations on the traceability graph, bound to one actor."""

    def __init__(self, storage: Storage, actor: Actor, *, readonly: bool = False) -> None:
        self._storage = storage
        self.actor = actor
        self.readonly = readonly

    # ------------------------------------------------------------------ reads

    def get_item(self, item_id: str) -> Item:
        """Return an item or raise ``NotFoundError``."""
        return self._require(item_id)

    def list_items(
        self,
        *,
        item_type: ItemType | None = None,
        status: Status | None = None,
        parent_id: str | None = None,
        query: str | None = None,
    ) -> list[Item]:
        """List items, optionally filtered, ordered by hierarchy level then number."""
        needle = query.lower() if query else None
        result = [
            item
            for item in self._storage.all()
            if (item_type is None or item.type is item_type)
            and (status is None or item.status is status)
            and (parent_id is None or item.parent == parent_id)
            and (needle is None or needle in item.title.lower() or needle in item.body.lower())
        ]
        return sorted(result, key=_sort_key)

    def get_overview(self) -> Overview:
        """Summarize item counts, requirement coverage and open gaps."""
        graph = Graph(self._storage.all())
        items = graph.items()
        reqs = graph.items(ItemType.REQ)
        covered = [r for r in reqs if graph.specs_for(r.id) and graph.verifications_for(r.id)]
        gaps = self.list_gaps()
        return Overview(
            total_items=len(items),
            by_type={t.value: sum(1 for i in items if i.type is t) for t in ItemType},
            by_status={s.value: sum(1 for i in items if i.status is s) for s in Status},
            coverage_percent=round(100 * len(covered) / len(reqs), 1) if reqs else 100.0,
            gaps=gaps.total,
            stale=len(gaps.stale),
        )

    def get_context(self, item_id: str, depth: int | None = None) -> Context:
        """Return an item with its ancestor chain and everything below it.

        ``depth`` limits how many levels of descendants are included (``None`` = all).
        """
        item = self._require(item_id)
        graph = Graph(self._storage.all())
        return Context(
            item=item,
            ancestors=graph.ancestors(item_id),
            descendants=sorted(graph.descendants(item_id, depth), key=_sort_key),
        )

    def trace(self, item_id: str, direction: Literal["up", "down", "both"] = "both") -> Trace:
        """Follow traceability links upstream (to the epic) and/or downstream (to verifications)."""
        item = self._require(item_id)
        graph = Graph(self._storage.all())
        return Trace(
            item=item,
            upstream=sorted(graph.upstream(item_id), key=_sort_key) if direction != "down" else [],
            downstream=(
                sorted(graph.descendants(item_id), key=_sort_key) if direction != "up" else []
            ),
        )

    def next_work(self, limit: int = 10) -> list[Item]:
        """Approved requirements and specs that are ready to implement.

        A spec is ready only when its parent requirement is itself approved or further along.
        Results are ordered by hierarchy level, then number.
        """
        graph = Graph(self._storage.all())
        ready_parent = {Status.APPROVED, Status.IMPLEMENTED, Status.VERIFIED}
        ready: list[Item] = []
        for item in graph.items():
            if item.status is not Status.APPROVED or item.type not in (ItemType.REQ, ItemType.SPEC):
                continue
            parent = graph.get(item.parent) if item.parent else None
            if item.type is ItemType.SPEC and (parent is None or parent.status not in ready_parent):
                continue
            ready.append(item)
        return sorted(ready, key=_sort_key)[: max(limit, 0)]

    def list_gaps(self, scope_id: str | None = None) -> Gaps:
        """Report traceability gaps, optionally limited to ``scope_id`` and its dependents."""
        graph = Graph(self._storage.all())
        if scope_id is not None:
            self._require(scope_id)
            scope = {scope_id, *graph.dependents(scope_id)}
        else:
            scope = {item.id for item in graph.items()}

        gaps = Gaps()
        for item in sorted(graph.items(), key=_sort_key):
            if item.id not in scope:
                continue
            if item.status is Status.STALE:
                gaps.stale.append(item.id)
            if item.type is ItemType.REQ:
                if not graph.specs_for(item.id):
                    gaps.reqs_without_spec.append(item.id)
                if not graph.verifications_for(item.id):
                    gaps.reqs_without_verification.append(item.id)
            elif item.type is ItemType.SPEC and not graph.verifications_for(item.id):
                gaps.specs_without_verification.append(item.id)
            elif item.result is VerificationResult.FAIL:
                gaps.failed_verifications.append(item.id)
        return gaps

    # ----------------------------------------------------------------- writes

    def create_item(
        self,
        item_type: ItemType,
        title: str,
        *,
        parent_id: str | None = None,
        body: str = "",
    ) -> Item:
        """Create an item in ``draft`` status under a valid parent."""
        self._require_writable()
        validate_parent(item_type, parent_id)
        if parent_id is not None:
            self._require(parent_id)
        item = self._build(
            id=format_id(item_type, self._storage.next_number(item_type)),
            type=item_type,
            title=title,
            parent=parent_id,
            body=body,
        )
        self._storage.save(item)
        self._audit("create_item", item.id, parent=parent_id)
        return item

    def update_item(self, item_id: str, patch: dict[str, Any], expected_revision: str) -> Item:
        """Edit title/body using optimistic concurrency.

        Editing a reviewed item sends it back to ``proposed`` and marks everything that
        depends on it as ``stale``.
        """
        self._require_writable()
        item = self._require(item_id)
        if item.revision != expected_revision:
            raise RevisionConflictError(
                f"{item_id} changed since it was read.",
                hint=f"Re-read the item (current revision: {item.revision}) and retry.",
                current_revision=item.revision,
            )
        unknown = set(patch) - EDITABLE_FIELDS
        if unknown:
            raise ValidationFailedError(
                f"Fields cannot be edited: {', '.join(sorted(unknown))}.",
                hint=f"Editable fields: {', '.join(sorted(EDITABLE_FIELDS))}.",
                fields=sorted(unknown),
            )
        updated = self._build(**{**item.model_dump(), **patch})
        if updated == item:
            return item
        previous = item.status
        updated.status = status_after_edit(previous)
        self._storage.save(updated)
        self._audit("update_item", item_id, fields=sorted(patch), previous_status=previous.value)
        if previous in _REVIEWED:
            self._mark_dependents_stale(item_id)
        return updated

    def propose_item(self, item_id: str) -> Item:
        """Move an item from ``draft`` to ``proposed`` (requests human review)."""
        return self._transition(item_id, Status.PROPOSED, "propose_item")

    def approve_item(self, item_id: str) -> Item:
        """Approve a proposed item. Reserved for human actors."""
        return self._transition(item_id, Status.APPROVED, "approve_item")

    def mark_implemented(self, item_id: str, evidence: str = "") -> Item:
        """Mark an approved requirement or spec as implemented."""
        item = self._require(item_id)
        if item.type not in (ItemType.REQ, ItemType.SPEC):
            raise ValidationFailedError(
                f"Only requirements and specs can be implemented, not a {item.type.value}.",
                field="id",
            )
        self._transition(item_id, Status.IMPLEMENTED, "mark_implemented", evidence=evidence)
        self._refresh_verified(item_id)
        return self._require(item_id)

    def link_items(self, from_id: str, to_id: str, relation: Relation) -> Item:
        """Add a ``satisfies`` (spec to req) or ``verifies`` (verification to req/spec) link."""
        return self._change_link(from_id, to_id, relation, add=True)

    def unlink_items(self, from_id: str, to_id: str, relation: Relation) -> Item:
        """Remove a previously created link."""
        return self._change_link(from_id, to_id, relation, add=False)

    def report_verification(
        self,
        item_id: str,
        result: VerificationResult,
        *,
        evidence: str = "",
        run_ref: str | None = None,
    ) -> Item:
        """Record the outcome of a verification and re-derive the status of its targets.

        A requirement or spec becomes ``verified`` once it is ``implemented`` and all its
        verifications passed; a failure on a ``verified`` item sends it to ``stale``.
        """
        self._require_writable()
        item = self._require(item_id)
        if item.type is not ItemType.VERIFICATION:
            raise ValidationFailedError(
                f"Results can only be reported on verifications, not a {item.type.value}.",
                field="id",
            )
        item.result, item.evidence, item.run_ref = result, evidence, run_ref
        self._storage.save(item)
        self._audit("report_verification", item_id, result=result.value, run_ref=run_ref)
        for target in dict.fromkeys([item.parent, *item.verifies]):
            if target is not None:
                self._refresh_verified(target)
        return item

    # -------------------------------------------------------------- internals

    def _require(self, item_id: str) -> Item:
        parse_id(item_id)  # Validates the format before touching storage.
        item = self._storage.get(item_id)
        if item is None:
            raise NotFoundError(
                f"Item {item_id} does not exist.",
                hint="Use list_items to find valid ids.",
                id=item_id,
            )
        return item

    def _require_writable(self) -> None:
        if self.readonly:
            raise ReadonlyModeError(
                "The workspace is in read-only mode.",
                hint="Restart without --readonly to allow changes.",
            )

    @staticmethod
    def _build(**data: Any) -> Item:
        try:
            return Item.model_validate(data)
        except ValidationError as error:
            first = error.errors()[0]
            field = ".".join(str(part) for part in first["loc"])
            raise ValidationFailedError(
                f"Invalid value for '{field}': {first['msg']}.",
                field=field,
            ) from error

    def _transition(self, item_id: str, target: Status, action: str, **extra: Any) -> Item:
        self._require_writable()
        item = self._require(item_id)
        check_transition(item.status, target, self.actor)
        previous = item.status
        item.status = target
        self._storage.save(item)
        self._audit(action, item_id, from_status=previous.value, to_status=target.value, **extra)
        return item

    def _change_link(self, from_id: str, to_id: str, relation: Relation, *, add: bool) -> Item:
        self._require_writable()
        source = self._require(from_id)
        target = self._require(to_id)
        allowed_sources, allowed_targets = {
            "satisfies": (ItemType.SPEC, {ItemType.REQ}),
            "verifies": (ItemType.VERIFICATION, {ItemType.REQ, ItemType.SPEC}),
        }[relation]
        if source.type is not allowed_sources or target.type not in allowed_targets:
            raise ValidationFailedError(
                f"A '{relation}' link cannot go from a {source.type.value} "
                f"to a {target.type.value}.",
                hint="satisfies: spec -> req; verifies: verification -> req or spec.",
                relation=relation,
            )
        links: list[str] = getattr(source, relation)
        if add:
            if to_id == source.parent:
                raise ValidationFailedError(
                    f"{to_id} is already the parent of {from_id}.",
                    hint="The parent link is implicit; no extra link is needed.",
                )
            if to_id not in links:
                links.append(to_id)
        else:
            if to_id not in links:
                raise NotFoundError(
                    f"No '{relation}' link from {from_id} to {to_id}.",
                    hint="Check the item's current links with get_item.",
                )
            links.remove(to_id)
        self._storage.save(source)
        self._audit("link_items" if add else "unlink_items", from_id, to=to_id, relation=relation)
        return source

    def _mark_dependents_stale(self, root_id: str) -> None:
        graph = Graph(self._storage.all())
        for dependent_id in sorted(graph.dependents(root_id)):
            dependent = self._storage.get(dependent_id)
            if dependent is None or dependent.status not in _STALEABLE:
                continue
            check_transition(dependent.status, Status.STALE, Actor.SYSTEM)
            dependent.status = Status.STALE
            self._storage.save(dependent)
            self._audit("mark_stale", dependent_id, actor=Actor.SYSTEM, caused_by=root_id)

    def _refresh_verified(self, item_id: str) -> None:
        """Derive ``verified`` (or ``stale`` after a failure) from verification results."""
        graph = Graph(self._storage.all())
        item = graph.get(item_id)
        if item is None or item.type not in (ItemType.REQ, ItemType.SPEC):
            return
        verifications = graph.verifications_for(item_id)
        if item.status is Status.IMPLEMENTED:
            if verifications and all(v.result is VerificationResult.PASS for v in verifications):
                self._system_transition(item, Status.VERIFIED)
        elif item.status is Status.VERIFIED and any(
            v.result is VerificationResult.FAIL for v in verifications
        ):
            self._system_transition(item, Status.STALE)

    def _system_transition(self, item: Item, target: Status) -> None:
        check_transition(item.status, target, Actor.SYSTEM)
        previous = item.status
        item.status = target
        self._storage.save(item)
        self._audit(
            "derive_status",
            item.id,
            actor=Actor.SYSTEM,
            from_status=previous.value,
            to_status=target.value,
        )

    def _audit(
        self, action: str, item_id: str, *, actor: Actor | None = None, **extra: Any
    ) -> None:
        self._storage.append_log(
            {
                "ts": datetime.now(UTC).isoformat(timespec="seconds"),
                "actor": (actor or self.actor).value,
                "action": action,
                "id": item_id,
                **extra,
            }
        )


def _sort_key(item: Item) -> tuple[int, int]:
    return _TYPE_ORDER.index(item.type), parse_id(item.id)[1]
