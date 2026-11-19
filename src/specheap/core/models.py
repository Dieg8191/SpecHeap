"""Domain models for the SDD traceability graph."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from specheap.core.errors import InvalidParentError, ValidationFailedError
from specheap.core.ids import parse_id


class ItemType(StrEnum):
    """Levels of the SDD hierarchy."""

    EPIC = "epic"
    FEATURE = "feature"
    REQ = "req"
    SPEC = "spec"
    VERIFICATION = "verification"


class Status(StrEnum):
    """Lifecycle status of an item."""

    DRAFT = "draft"
    PROPOSED = "proposed"
    APPROVED = "approved"
    IMPLEMENTED = "implemented"
    VERIFIED = "verified"
    STALE = "stale"


class VerificationResult(StrEnum):
    """Outcome of a verification run."""

    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"


class Actor(StrEnum):
    """Who performs an action.

    ``SYSTEM`` is used for derived transitions (for example ``verified`` and ``stale``)
    that no interface can request directly.
    """

    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"


# Allowed parent types for each item type. Epics are roots.
PARENT_TYPES: dict[ItemType, frozenset[ItemType]] = {
    ItemType.EPIC: frozenset(),
    ItemType.FEATURE: frozenset({ItemType.EPIC}),
    ItemType.REQ: frozenset({ItemType.FEATURE}),
    ItemType.SPEC: frozenset({ItemType.REQ}),
    ItemType.VERIFICATION: frozenset({ItemType.REQ, ItemType.SPEC}),
}


def validate_parent(child_type: ItemType, parent_id: str | None) -> None:
    """Check that ``parent_id`` is a valid parent for an item of ``child_type``.

    Raises:
        InvalidParentError: if the parent is missing, unexpected or of the wrong type.
    """
    allowed = PARENT_TYPES[child_type]
    if not allowed:
        if parent_id is not None:
            raise InvalidParentError(
                f"A {child_type.value} is a root item and cannot have a parent.",
                hint="Omit parent_id when creating an epic.",
            )
        return
    if parent_id is None:
        expected = ", ".join(sorted(t.value for t in allowed))
        raise InvalidParentError(
            f"A {child_type.value} requires a parent of type: {expected}.",
            hint="Provide parent_id pointing to an existing item of the expected type.",
        )
    parent_type, _ = parse_id(parent_id)
    if parent_type not in allowed:
        expected = ", ".join(sorted(t.value for t in allowed))
        raise InvalidParentError(
            f"A {child_type.value} cannot be a child of a {parent_type.value}; "
            f"expected: {expected}.",
            hint="Check the hierarchy: epic > feature > req > spec > verification.",
        )


class Item(BaseModel):
    """A node in the traceability graph.

    Links are stored on the child side only (``parent``, ``satisfies``, ``verifies``);
    inverse links are computed by the index.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: str
    type: ItemType
    title: str = Field(min_length=1, max_length=200)
    status: Status = Status.DRAFT
    parent: str | None = None
    body: str = ""
    satisfies: list[str] = Field(default_factory=list)
    verifies: list[str] = Field(default_factory=list)
    # Only meaningful for verifications: the latest reported run.
    result: VerificationResult | None = None
    evidence: str = ""
    run_ref: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Item:
        if self.type is not ItemType.VERIFICATION and self.result is not None:
            raise ValueError("Only verifications can carry a result.")
        id_type, _ = parse_id(self.id)
        if id_type is not self.type:
            raise ValueError(f"Identifier {self.id} does not belong to a {self.type.value}.")
        return self

    @field_validator("id")
    @classmethod
    def _id_is_well_formed(cls, value: str) -> str:
        try:
            parse_id(value)
        except ValidationFailedError as error:
            # Pydantic only wraps ValueError into its own ValidationError.
            raise ValueError(error.message) from error
        return value

    @property
    def revision(self) -> str:
        """Content hash used for optimistic concurrency control."""
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
