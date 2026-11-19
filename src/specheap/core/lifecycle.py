"""Lifecycle rules: which status transitions exist and who may perform them.

The transition table below is the single source of truth. Every interface (MCP, CLI, web)
must go through ``check_transition`` so that rules cannot be bypassed.
"""

from __future__ import annotations

from specheap.core.errors import ForbiddenForAgentError, InvalidTransitionError
from specheap.core.models import Actor, Status

_HUMAN_OR_AGENT = frozenset({Actor.HUMAN, Actor.AGENT})
_HUMAN_ONLY = frozenset({Actor.HUMAN})
_SYSTEM_ONLY = frozenset({Actor.SYSTEM})

# (from, to) -> actors allowed to perform the transition.
TRANSITIONS: dict[tuple[Status, Status], frozenset[Actor]] = {
    # Proposal and review.
    (Status.DRAFT, Status.PROPOSED): _HUMAN_OR_AGENT,
    (Status.PROPOSED, Status.APPROVED): _HUMAN_ONLY,
    # Delivery.
    (Status.APPROVED, Status.IMPLEMENTED): _HUMAN_OR_AGENT,
    # Derived: all verifications of an item passed.
    (Status.IMPLEMENTED, Status.VERIFIED): _SYSTEM_ONLY,
    # Derived: an upstream item changed and this one needs review.
    (Status.PROPOSED, Status.STALE): _SYSTEM_ONLY,
    (Status.APPROVED, Status.STALE): _SYSTEM_ONLY,
    (Status.IMPLEMENTED, Status.STALE): _SYSTEM_ONLY,
    (Status.VERIFIED, Status.STALE): _SYSTEM_ONLY,
    # Clearing ``stale`` is a review act: only a human may confirm the item is still valid.
    # Agents clear it indirectly by editing the item, which resets it to ``proposed``.
    (Status.STALE, Status.APPROVED): _HUMAN_ONLY,
    (Status.STALE, Status.PROPOSED): _HUMAN_OR_AGENT,
}

# Statuses that fall back to ``proposed`` when the item content is edited.
_RESET_ON_EDIT = frozenset(
    {Status.APPROVED, Status.IMPLEMENTED, Status.VERIFIED, Status.STALE}
)


def check_transition(current: Status, target: Status, actor: Actor) -> None:
    """Validate a lifecycle transition for the given actor.

    Raises:
        InvalidTransitionError: if the transition does not exist or the actor is SYSTEM-only
            and a different actor requested it.
        ForbiddenForAgentError: if the transition exists but is reserved for humans.
    """
    allowed = TRANSITIONS.get((current, target))
    if allowed is None:
        raise InvalidTransitionError(
            f"Cannot move from '{current.value}' to '{target.value}'.",
            hint=_hint_for(current),
            current=current.value,
            target=target.value,
        )
    if actor in allowed:
        return
    if actor is Actor.AGENT and Actor.HUMAN in allowed:
        raise ForbiddenForAgentError(
            f"Moving from '{current.value}' to '{target.value}' is reserved for humans.",
            hint="Use propose_item to request a human review instead.",
            current=current.value,
            target=target.value,
        )
    raise InvalidTransitionError(
        f"Actor '{actor.value}' cannot move from '{current.value}' to '{target.value}'.",
        hint="This transition is derived automatically and cannot be requested directly.",
        current=current.value,
        target=target.value,
    )


def status_after_edit(current: Status) -> Status:
    """Return the status an item takes after its content is edited."""
    return Status.PROPOSED if current in _RESET_ON_EDIT else current


def _hint_for(current: Status) -> str:
    next_steps = sorted(target.value for (source, target) in TRANSITIONS if source is current)
    if not next_steps:
        return f"No transitions are available from '{current.value}'."
    return f"From '{current.value}' you can move to: {', '.join(next_steps)}."
