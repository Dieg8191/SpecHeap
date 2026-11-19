"""Multi-step service operations are all-or-nothing."""

from __future__ import annotations

import pytest

from specheap.core.models import Actor, Item, ItemType, Status, VerificationResult
from specheap.core.ports import Storage
from specheap.core.service import Service
from tests.test_service import approve, build_chain


class Boom(RuntimeError):
    """The injected failure."""


def fail_on_call(storage: Storage, monkeypatch: pytest.MonkeyPatch, method: str, call: int) -> None:
    """Make the ``call``-th invocation of ``storage.<method>`` raise ``Boom``."""
    original = getattr(storage, method)
    counter = {"calls": 0}

    def flaky(*args: object, **kwargs: object) -> object:
        counter["calls"] += 1
        if counter["calls"] == call:
            raise Boom(f"injected failure in {method} call {call}")
        return original(*args, **kwargs)

    monkeypatch.setattr(storage, method, flaky)


def snapshot(storage: Storage) -> tuple[dict[str, Item], list[dict[str, object]]]:
    return {item.id: item for item in storage.all()}, storage.log_entries()


def approved_chain(storage: Storage) -> tuple[Service, Service]:
    human = Service(storage, Actor.HUMAN)
    agent = Service(storage, Actor.AGENT)
    chain = build_chain(human)
    for key in ("req", "spec", "ver"):
        approve(human, chain[key].id)
    return human, agent


def test_failure_halfway_through_stale_propagation_changes_nothing(
    storage: Storage, monkeypatch: pytest.MonkeyPatch
) -> None:
    human, agent = approved_chain(storage)
    before = snapshot(storage)
    revision = human.get_item("REQ-001").revision

    # Calls: 1 saves the edited requirement, 2 stales the spec, 3 would stale the verification.
    fail_on_call(storage, monkeypatch, "save", call=3)
    with pytest.raises(Boom):
        agent.update_item("REQ-001", {"body": "Changed meaning"}, revision)

    assert snapshot(storage) == before
    assert human.get_item("REQ-001").status is Status.APPROVED
    assert human.get_item("SPEC-001").status is Status.APPROVED


def test_the_same_edit_succeeds_once_the_failure_is_gone(
    storage: Storage, monkeypatch: pytest.MonkeyPatch
) -> None:
    human, agent = approved_chain(storage)
    revision = human.get_item("REQ-001").revision
    with monkeypatch.context() as patch:
        fail_on_call(storage, patch, "save", call=2)
        with pytest.raises(Boom):
            agent.update_item("REQ-001", {"body": "Changed meaning"}, revision)

    agent.update_item("REQ-001", {"body": "Changed meaning"}, revision)
    assert human.get_item("REQ-001").status is Status.PROPOSED
    assert human.get_item("SPEC-001").status is Status.STALE
    assert human.get_item("VER-001").status is Status.STALE


def test_failure_while_deriving_verified_keeps_the_previous_state(
    storage: Storage, monkeypatch: pytest.MonkeyPatch
) -> None:
    human, agent = approved_chain(storage)
    human.report_verification("VER-001", VerificationResult.PASS)
    before = snapshot(storage)

    # Call 1 saves ``implemented``; call 2 would derive ``verified``.
    fail_on_call(storage, monkeypatch, "save", call=2)
    with pytest.raises(Boom):
        agent.mark_implemented("REQ-001")

    assert snapshot(storage) == before
    assert human.get_item("REQ-001").status is Status.APPROVED


def test_failure_after_recording_a_result_discards_the_result(
    storage: Storage, monkeypatch: pytest.MonkeyPatch
) -> None:
    human, agent = approved_chain(storage)
    human.mark_implemented("REQ-001")
    before = snapshot(storage)

    # Call 1 saves the result on the verification; call 2 would derive ``verified``.
    fail_on_call(storage, monkeypatch, "save", call=2)
    with pytest.raises(Boom):
        agent.report_verification("VER-001", VerificationResult.PASS, evidence="ci")

    assert snapshot(storage) == before
    assert human.get_item("VER-001").result is None
    assert human.get_item("REQ-001").status is Status.IMPLEMENTED


def test_failed_creation_leaves_no_item_and_reuses_the_number(
    storage: Storage, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = Service(storage, Actor.AGENT)
    with monkeypatch.context() as patch:
        fail_on_call(storage, patch, "append_log", call=1)
        with pytest.raises(Boom):
            agent.create_item(ItemType.EPIC, "Never created")

    assert storage.all() == []
    assert agent.create_item(ItemType.EPIC, "Created").id == "EPIC-001"


def test_audit_entries_are_committed_together_with_the_change(storage: Storage) -> None:
    human, agent = approved_chain(storage)
    before = len(storage.log_entries())
    agent.update_item("REQ-001", {"body": "Changed meaning"}, human.get_item("REQ-001").revision)
    actions = [e["action"] for e in storage.log_entries()[before:]]
    assert actions == ["update_item", "mark_stale", "mark_stale"]


def test_readonly_service_does_not_open_a_transaction(storage: Storage) -> None:
    class Spy:
        def __init__(self, inner: Storage) -> None:
            self.inner = inner
            self.transactions = 0

        def transaction(self):  # noqa: ANN202
            self.transactions += 1
            return self.inner.transaction()

        def __getattr__(self, name: str):  # noqa: ANN204
            return getattr(self.inner, name)

    spy = Spy(storage)
    reader = Service(spy, Actor.AGENT, readonly=True)  # type: ignore[arg-type]
    with pytest.raises(Exception, match="read-only"):
        reader.create_item(ItemType.EPIC, "x")
    assert spy.transactions == 0
