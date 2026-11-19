"""Tests for the lifecycle transition matrix."""

from __future__ import annotations

import itertools

import pytest

from specheap.core import (
    ForbiddenForAgentError,
    InvalidTransitionError,
    check_transition,
    status_after_edit,
)
from specheap.core.lifecycle import TRANSITIONS
from specheap.core.models import Actor, Status


@pytest.mark.parametrize(
    ("current", "target", "actor"),
    [
        (Status.DRAFT, Status.PROPOSED, Actor.AGENT),
        (Status.DRAFT, Status.PROPOSED, Actor.HUMAN),
        (Status.PROPOSED, Status.APPROVED, Actor.HUMAN),
        (Status.APPROVED, Status.IMPLEMENTED, Actor.AGENT),
        (Status.APPROVED, Status.IMPLEMENTED, Actor.HUMAN),
        (Status.IMPLEMENTED, Status.VERIFIED, Actor.SYSTEM),
        (Status.APPROVED, Status.STALE, Actor.SYSTEM),
        (Status.STALE, Status.APPROVED, Actor.HUMAN),
        (Status.STALE, Status.PROPOSED, Actor.AGENT),
    ],
)
def test_allowed_transitions(current: Status, target: Status, actor: Actor) -> None:
    check_transition(current, target, actor)


def test_agent_cannot_approve() -> None:
    with pytest.raises(ForbiddenForAgentError) as exc:
        check_transition(Status.PROPOSED, Status.APPROVED, Actor.AGENT)
    assert exc.value.code == "FORBIDDEN_FOR_AGENT"
    assert exc.value.hint


def test_agent_cannot_clear_stale_by_approving() -> None:
    with pytest.raises(ForbiddenForAgentError):
        check_transition(Status.STALE, Status.APPROVED, Actor.AGENT)


@pytest.mark.parametrize("actor", [Actor.HUMAN, Actor.AGENT])
def test_verified_cannot_be_requested_directly(actor: Actor) -> None:
    with pytest.raises(InvalidTransitionError):
        check_transition(Status.IMPLEMENTED, Status.VERIFIED, actor)


@pytest.mark.parametrize("actor", [Actor.HUMAN, Actor.AGENT])
def test_stale_cannot_be_requested_directly(actor: Actor) -> None:
    with pytest.raises(InvalidTransitionError):
        check_transition(Status.APPROVED, Status.STALE, actor)


def test_unknown_transition_is_invalid_and_hints_next_steps() -> None:
    with pytest.raises(InvalidTransitionError) as exc:
        check_transition(Status.DRAFT, Status.APPROVED, Actor.HUMAN)
    assert exc.value.code == "INVALID_TRANSITION"
    assert "proposed" in (exc.value.hint or "")


def test_every_pair_outside_the_table_is_invalid() -> None:
    for current, target in itertools.product(Status, Status):
        if (current, target) in TRANSITIONS:
            continue
        for actor in Actor:
            with pytest.raises(InvalidTransitionError):
                check_transition(current, target, actor)


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (Status.DRAFT, Status.DRAFT),
        (Status.PROPOSED, Status.PROPOSED),
        (Status.APPROVED, Status.PROPOSED),
        (Status.IMPLEMENTED, Status.PROPOSED),
        (Status.VERIFIED, Status.PROPOSED),
        (Status.STALE, Status.PROPOSED),
    ],
)
def test_status_after_edit(current: Status, expected: Status) -> None:
    assert status_after_edit(current) is expected
