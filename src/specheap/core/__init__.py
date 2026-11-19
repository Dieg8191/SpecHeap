"""Core domain: models, identifiers, lifecycle rules and errors.

This package must not import from the MCP, CLI or web layers.
"""

from specheap.core.errors import (
    ForbiddenForAgentError,
    InvalidParentError,
    InvalidTransitionError,
    NotFoundError,
    ReadonlyModeError,
    RevisionConflictError,
    SpecHeapError,
    ValidationFailedError,
)
from specheap.core.ids import format_id, parse_id
from specheap.core.lifecycle import check_transition, status_after_edit
from specheap.core.models import Actor, Item, ItemType, Status, validate_parent

__all__ = [
    "Actor",
    "ForbiddenForAgentError",
    "InvalidParentError",
    "InvalidTransitionError",
    "Item",
    "ItemType",
    "NotFoundError",
    "ReadonlyModeError",
    "RevisionConflictError",
    "SpecHeapError",
    "Status",
    "ValidationFailedError",
    "check_transition",
    "format_id",
    "parse_id",
    "status_after_edit",
    "validate_parent",
]
