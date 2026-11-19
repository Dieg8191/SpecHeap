"""Wire-level views shared by the interface adapters (MCP server and web API).

These models describe items and their relations as seen from outside the core, including the
``revision`` token needed for optimistic concurrency.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from specheap.core.models import Item, ItemType, Status, VerificationResult
from specheap.core.service import Context


class ItemDTO(BaseModel):
    """An item as seen by clients, including its concurrency token."""

    id: str
    type: ItemType
    title: str
    status: Status
    parent: str | None
    body: str
    satisfies: list[str]
    verifies: list[str]
    result: VerificationResult | None
    evidence: str
    run_ref: str | None
    revision: str

    @classmethod
    def from_item(cls, item: Item) -> ItemDTO:
        return cls(**item.model_dump(), revision=item.revision)


class ContextDTO(BaseModel):
    """An item with its ancestors and descendants."""

    item: ItemDTO
    ancestors: list[ItemDTO]
    descendants: list[ItemDTO]


class TraceDTO(BaseModel):
    """Traceability chains around an item."""

    item: ItemDTO
    upstream: list[ItemDTO] = Field(default_factory=list)
    downstream: list[ItemDTO] = Field(default_factory=list)


def to_dtos(items: list[Item]) -> list[ItemDTO]:
    """Convert a list of items to DTOs."""
    return [ItemDTO.from_item(i) for i in items]


def context_dto(context: Context) -> ContextDTO:
    """Convert a service ``Context`` to its wire representation."""
    return ContextDTO(
        item=ItemDTO.from_item(context.item),
        ancestors=to_dtos(context.ancestors),
        descendants=to_dtos(context.descendants),
    )
