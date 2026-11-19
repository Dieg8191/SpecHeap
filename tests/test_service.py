"""Tests for the Service layer: rules every interface relies on."""

from __future__ import annotations

import json

import pytest

from specheap.core.errors import (
    ForbiddenForAgentError,
    InvalidParentError,
    InvalidTransitionError,
    NotFoundError,
    ReadonlyModeError,
    RevisionConflictError,
    ValidationFailedError,
)
from specheap.core.models import Actor, Item, ItemType, Status, VerificationResult
from specheap.core.ports import Storage
from specheap.core.service import Service
from specheap.storage import FileSystemStorage, MemoryStorage


def build_chain(svc: Service) -> dict[str, Item]:
    """Create epic > feature > req > spec and a verification attached to the req."""
    epic = svc.create_item(ItemType.EPIC, "Authentication")
    feat = svc.create_item(ItemType.FEATURE, "Login", parent_id=epic.id)
    req = svc.create_item(ItemType.REQ, "Lock after 3 failures", parent_id=feat.id)
    spec = svc.create_item(ItemType.SPEC, "Counter in session store", parent_id=req.id)
    ver = svc.create_item(ItemType.VERIFICATION, "Lockout test", parent_id=req.id)
    return {"epic": epic, "feat": feat, "req": req, "spec": spec, "ver": ver}


def approve(human: Service, item_id: str) -> None:
    human.propose_item(item_id)
    human.approve_item(item_id)


def status_of(svc: Service, item_id: str) -> Status:
    return svc.get_item(item_id).status


# --------------------------------------------------------------- creation


def test_create_chain_assigns_sequential_ids_in_draft(human: Service) -> None:
    chain = build_chain(human)
    expected = ["EPIC-001", "FEAT-001", "REQ-001", "SPEC-001", "VER-001"]
    assert [i.id for i in chain.values()] == expected
    assert all(i.status is Status.DRAFT for i in chain.values())
    second = human.create_item(ItemType.REQ, "Another", parent_id="FEAT-001")
    assert second.id == "REQ-002"


def test_create_validates_parent(human: Service) -> None:
    with pytest.raises(InvalidParentError):
        human.create_item(ItemType.REQ, "No parent")
    with pytest.raises(NotFoundError):
        human.create_item(ItemType.FEATURE, "Orphan", parent_id="EPIC-099")
    epic = human.create_item(ItemType.EPIC, "E")
    with pytest.raises(InvalidParentError):
        human.create_item(ItemType.REQ, "Wrong level", parent_id=epic.id)


def test_create_rejects_empty_title(human: Service) -> None:
    with pytest.raises(ValidationFailedError) as exc:
        human.create_item(ItemType.EPIC, "")
    assert exc.value.details["field"] == "title"


# -------------------------------------------------------------- lifecycle


def test_agent_can_propose_but_not_approve(human: Service, agent: Service) -> None:
    req = build_chain(human)["req"]
    agent.propose_item(req.id)
    with pytest.raises(ForbiddenForAgentError):
        agent.approve_item(req.id)
    assert status_of(human, req.id) is Status.PROPOSED
    human.approve_item(req.id)
    assert status_of(human, req.id) is Status.APPROVED


def test_cannot_implement_before_approval(human: Service) -> None:
    req = build_chain(human)["req"]
    with pytest.raises(InvalidTransitionError):
        human.mark_implemented(req.id)


def test_only_reqs_and_specs_can_be_implemented(human: Service) -> None:
    epic = build_chain(human)["epic"]
    with pytest.raises(ValidationFailedError):
        human.mark_implemented(epic.id)


# ------------------------------------------------------------ concurrency


def test_update_with_stale_revision_conflicts(human: Service) -> None:
    req = build_chain(human)["req"]
    human.update_item(req.id, {"title": "Edited by human"}, req.revision)
    with pytest.raises(RevisionConflictError) as exc:
        human.update_item(req.id, {"title": "Edited by agent"}, req.revision)
    assert exc.value.details["current_revision"] != req.revision


def test_update_rejects_unmanaged_fields(human: Service) -> None:
    req = build_chain(human)["req"]
    with pytest.raises(ValidationFailedError):
        human.update_item(req.id, {"status": "approved"}, req.revision)


def test_noop_update_changes_nothing(human: Service) -> None:
    req = build_chain(human)["req"]
    result = human.update_item(req.id, {"title": req.title}, req.revision)
    assert result.revision == req.revision


# ------------------------------------------------------ stale propagation


def test_editing_approved_req_stales_dependents(human: Service, agent: Service) -> None:
    chain = build_chain(human)
    req, spec, ver = chain["req"], chain["spec"], chain["ver"]
    approve(human, req.id)
    approve(human, spec.id)  # Verification stays in draft.

    agent.update_item(req.id, {"body": "Changed meaning"}, human.get_item(req.id).revision)

    assert status_of(human, req.id) is Status.PROPOSED
    assert status_of(human, spec.id) is Status.STALE
    assert status_of(human, ver.id) is Status.DRAFT


def test_editing_unreviewed_item_does_not_stale_dependents(human: Service) -> None:
    chain = build_chain(human)
    approve(human, chain["spec"].id)
    req = chain["req"]
    human.update_item(req.id, {"title": "Draft tweak"}, req.revision)
    assert status_of(human, chain["spec"].id) is Status.APPROVED


def test_human_can_clear_stale_but_agent_cannot(human: Service, agent: Service) -> None:
    chain = build_chain(human)
    approve(human, chain["req"].id)
    approve(human, chain["spec"].id)
    human.update_item(chain["req"].id, {"title": "New"}, human.get_item("REQ-001").revision)
    with pytest.raises(ForbiddenForAgentError):
        agent.approve_item("SPEC-001")
    human.approve_item("SPEC-001")
    assert status_of(human, "SPEC-001") is Status.APPROVED


# ----------------------------------------------------- derived `verified`


def test_item_becomes_verified_when_all_verifications_pass(human: Service, agent: Service) -> None:
    chain = build_chain(human)
    req = chain["req"]
    approve(human, req.id)
    agent.mark_implemented(req.id, evidence="PR #1")
    assert status_of(human, req.id) is Status.IMPLEMENTED

    agent.report_verification("VER-001", VerificationResult.PASS, evidence="ci run 42")
    assert status_of(human, req.id) is Status.VERIFIED


def test_passing_before_implementation_verifies_on_implement(human: Service) -> None:
    chain = build_chain(human)
    req = chain["req"]
    human.report_verification("VER-001", VerificationResult.PASS)
    assert status_of(human, req.id) is Status.DRAFT
    approve(human, req.id)
    human.mark_implemented(req.id)
    assert status_of(human, req.id) is Status.VERIFIED


def test_failure_blocks_verified_and_stales_verified_items(human: Service) -> None:
    chain = build_chain(human)
    req = chain["req"]
    approve(human, req.id)
    human.mark_implemented(req.id)
    human.report_verification("VER-001", VerificationResult.FAIL)
    assert status_of(human, req.id) is Status.IMPLEMENTED

    human.report_verification("VER-001", VerificationResult.PASS)
    assert status_of(human, req.id) is Status.VERIFIED
    human.report_verification("VER-001", VerificationResult.FAIL, run_ref="run-43")
    assert status_of(human, req.id) is Status.STALE
    assert human.get_item("VER-001").run_ref == "run-43"


def test_report_verification_only_on_verifications(human: Service) -> None:
    req = build_chain(human)["req"]
    with pytest.raises(ValidationFailedError):
        human.report_verification(req.id, VerificationResult.PASS)


# ------------------------------------------------------------------ links


def test_link_rules(human: Service) -> None:
    chain = build_chain(human)
    other_req = human.create_item(ItemType.REQ, "Second req", parent_id="FEAT-001")

    linked = human.link_items("SPEC-001", other_req.id, "satisfies")
    assert linked.satisfies == [other_req.id]
    assert human.link_items("SPEC-001", other_req.id, "satisfies").satisfies == [other_req.id]
    assert human.get_item("SPEC-001").satisfies == [other_req.id]

    with pytest.raises(ValidationFailedError):
        human.link_items(chain["req"].id, other_req.id, "satisfies")  # req cannot satisfy
    with pytest.raises(ValidationFailedError):
        human.link_items("SPEC-001", chain["req"].id, "satisfies")  # already the parent
    with pytest.raises(ValidationFailedError):
        human.link_items("VER-001", chain["feat"].id, "verifies")  # feature is not verifiable

    human.unlink_items("SPEC-001", other_req.id, "satisfies")
    assert human.get_item("SPEC-001").satisfies == []
    with pytest.raises(NotFoundError):
        human.unlink_items("SPEC-001", other_req.id, "satisfies")


# ------------------------------------------------------------------- gaps


def test_list_gaps(human: Service) -> None:
    chain = build_chain(human)
    lonely = human.create_item(ItemType.REQ, "Lonely req", parent_id="FEAT-001")

    gaps = human.list_gaps()
    assert gaps.reqs_without_spec == [lonely.id]
    assert gaps.reqs_without_verification == [lonely.id]
    assert gaps.specs_without_verification == ["SPEC-001"]

    human.create_item(ItemType.VERIFICATION, "Spec check", parent_id="SPEC-001")
    human.report_verification("VER-001", VerificationResult.FAIL)
    gaps = human.list_gaps()
    assert gaps.specs_without_verification == []
    assert gaps.failed_verifications == ["VER-001"]

    scoped = human.list_gaps(scope_id=chain["req"].id)
    assert lonely.id not in scoped.reqs_without_spec


def test_list_items_filters_and_orders(human: Service) -> None:
    build_chain(human)
    human.create_item(ItemType.REQ, "Password reset", parent_id="FEAT-001")
    assert [i.id for i in human.list_items(item_type=ItemType.REQ)] == ["REQ-001", "REQ-002"]
    assert [i.id for i in human.list_items(query="reset")] == ["REQ-002"]
    assert [i.id for i in human.list_items(parent_id="REQ-001")] == ["SPEC-001", "VER-001"]
    assert human.list_items(status=Status.APPROVED) == []


# -------------------------------------------------------- readonly + audit


def test_readonly_blocks_writes_but_allows_reads(storage: Storage) -> None:
    writer = Service(storage, Actor.HUMAN)
    req = build_chain(writer)["req"]
    reader = Service(storage, Actor.AGENT, readonly=True)

    assert reader.get_item(req.id).title == req.title
    assert reader.list_gaps().total > 0
    with pytest.raises(ReadonlyModeError):
        reader.create_item(ItemType.EPIC, "Nope")
    with pytest.raises(ReadonlyModeError):
        reader.propose_item(req.id)
    with pytest.raises(ReadonlyModeError):
        reader.update_item(req.id, {"title": "x"}, req.revision)


def test_audit_log_records_actor_and_derived_changes(storage: Storage) -> None:
    human = Service(storage, Actor.HUMAN)
    agent = Service(storage, Actor.AGENT)
    chain = build_chain(human)
    approve(human, chain["req"].id)
    approve(human, chain["spec"].id)
    agent.update_item("REQ-001", {"title": "Changed"}, human.get_item("REQ-001").revision)

    if isinstance(storage, MemoryStorage):
        entries = storage.log
    else:
        assert isinstance(storage, FileSystemStorage)
        log_text = (storage.data_dir / "log.jsonl").read_text(encoding="utf-8")
        entries = [json.loads(line) for line in log_text.splitlines()]
    by_action = {e["action"]: e for e in entries}
    assert by_action["update_item"]["actor"] == "agent"
    assert by_action["approve_item"]["actor"] == "human"
    assert by_action["mark_stale"]["actor"] == "system"
    assert by_action["mark_stale"]["caused_by"] == "REQ-001"
