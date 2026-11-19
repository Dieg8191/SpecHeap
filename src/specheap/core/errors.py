"""Domain errors.

Every error carries a stable machine-readable ``code``, a human-readable ``message`` and an
optional ``hint`` with the suggested next step. Interfaces (MCP, CLI, web) translate these
into their own wire formats; the codes are part of the public contract.
"""

from __future__ import annotations

from typing import Any


class SpecHeapError(Exception):
    """Base class for all SpecHeap domain errors."""

    code: str = "SPECHEAP_ERROR"

    def __init__(self, message: str, *, hint: str | None = None, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        """Serialize the error into a JSON-friendly structure."""
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.hint:
            payload["hint"] = self.hint
        if self.details:
            payload["details"] = self.details
        return payload


class NotFoundError(SpecHeapError):
    """The requested item does not exist."""

    code = "NOT_FOUND"


class InvalidParentError(SpecHeapError):
    """The parent item type is not compatible with the child type."""

    code = "INVALID_PARENT"


class InvalidTransitionError(SpecHeapError):
    """The lifecycle transition is not allowed from the current status."""

    code = "INVALID_TRANSITION"


class ForbiddenForAgentError(SpecHeapError):
    """The action is reserved for human actors."""

    code = "FORBIDDEN_FOR_AGENT"


class RevisionConflictError(SpecHeapError):
    """The provided revision is stale; the item changed since it was read."""

    code = "REVISION_CONFLICT"


class ValidationFailedError(SpecHeapError):
    """Input failed validation."""

    code = "VALIDATION_ERROR"


class StorageError(SpecHeapError):
    """The storage back end cannot be used (corrupt, locked or from a newer version)."""

    code = "STORAGE_ERROR"


class ReadonlyModeError(SpecHeapError):
    """A write was attempted while the server runs in read-only mode."""

    code = "READONLY_MODE"
