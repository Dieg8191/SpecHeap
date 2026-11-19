"""Tests for the web UI: rendering, actions and its security boundary."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from specheap.core.models import Actor, ItemType, Status, VerificationResult
from specheap.core.ports import Storage
from specheap.core.service import Service
from specheap.web import create_app

TOKEN = "test-token"


@pytest.fixture
def agent(storage: Storage) -> Service:
    return Service(storage, Actor.AGENT)


@pytest.fixture
def client(storage: Storage) -> TestClient:
    app = create_app(storage, csrf_token=TOKEN)
    return TestClient(app, base_url="http://localhost", follow_redirects=False)


def seed(agent: Service) -> None:
    """Epic > feature > req (proposed) > spec + verification, plus a req with no spec."""
    epic = agent.create_item(ItemType.EPIC, "Authentication")
    feat = agent.create_item(ItemType.FEATURE, "Login", parent_id=epic.id)
    req = agent.create_item(
        ItemType.REQ, "Lock after failures", parent_id=feat.id, body="WHEN 3 failures, LOCK."
    )
    agent.create_item(ItemType.SPEC, "Counter", parent_id=req.id)
    agent.create_item(ItemType.VERIFICATION, "Lockout test", parent_id=req.id)
    agent.create_item(ItemType.REQ, "Password reset", parent_id=feat.id)
    agent.propose_item(req.id)


def post(client: TestClient, path: str, **data: str) -> object:
    return client.post(path, data={"csrf_token": TOKEN, **data})


# ----------------------------------------------------------------- rendering


def test_empty_workspace_renders(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "No items yet" in response.text


def test_dashboard_shows_review_queue_gaps_and_tree(client: TestClient, agent: Service) -> None:
    seed(agent)
    page = client.get("/").text
    assert "Awaiting your review (1)" in page
    assert "REQ-001" in page and "Lock after failures" in page
    assert "no spec" in page  # REQ-002 has no spec
    assert "Requirements without a spec" in page
    assert "Authentication" in page and "Counter" in page
    assert 'action="/items/REQ-001/approve"' in page


def test_item_page_shows_context(client: TestClient, agent: Service) -> None:
    seed(agent)
    page = client.get("/items/REQ-001").text
    assert "REQ-001: Lock after failures" in page
    assert 'href="/items/EPIC-001"' in page and 'href="/items/FEAT-001"' in page  # breadcrumbs
    assert "SPEC-001" in page and "VER-001" in page  # children
    assert "WHEN 3 failures, LOCK." in page
    assert agent.get_item("REQ-001").revision in page


def test_verification_page_shows_result(client: TestClient, agent: Service) -> None:
    seed(agent)
    agent.report_verification(
        "VER-001", VerificationResult.FAIL, evidence="assertion failed", run_ref="run-7"
    )
    page = client.get("/items/VER-001").text
    assert "fail" in page and "run-7" in page and "assertion failed" in page


def test_unknown_or_malformed_item_is_404(client: TestClient) -> None:
    missing = client.get("/items/REQ-099")
    assert missing.status_code == 404 and "NOT_FOUND" in missing.text
    malformed = client.get("/items/nope")
    assert malformed.status_code == 404 and "VALIDATION_ERROR" in malformed.text


def test_user_content_is_escaped(client: TestClient, agent: Service) -> None:
    epic = agent.create_item(ItemType.EPIC, "<img src=x onerror=alert(1)>")
    agent.update_item(epic.id, {"body": "<script>alert(1)</script>"}, epic.revision)
    for path in ("/", "/items/EPIC-001"):
        page = client.get(path).text
        assert "<script>" not in page and "<img src=x" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in client.get("/items/EPIC-001").text


@pytest.mark.parametrize(
    ("status", "expected", "absent"),
    [
        (Status.DRAFT, "Propose for review", "Approve"),
        (Status.PROPOSED, "Approve", "Propose for review"),
        (Status.APPROVED, "Mark implemented", "Approve"),
    ],
)
def test_actions_match_status(
    client: TestClient, agent: Service, status: Status, expected: str, absent: str
) -> None:
    human = Service(agent._storage, Actor.HUMAN)  # noqa: SLF001
    epic = agent.create_item(ItemType.EPIC, "E")
    feat = agent.create_item(ItemType.FEATURE, "F", parent_id=epic.id)
    req = agent.create_item(ItemType.REQ, "R", parent_id=feat.id)
    if status in (Status.PROPOSED, Status.APPROVED):
        agent.propose_item(req.id)
    if status is Status.APPROVED:
        human.approve_item(req.id)
    page = client.get(f"/items/{req.id}").text
    assert f">{expected}<" in page
    assert f">{absent}<" not in page


def test_no_actions_on_approved_epic(client: TestClient, agent: Service) -> None:
    human = Service(agent._storage, Actor.HUMAN)  # noqa: SLF001
    epic = agent.create_item(ItemType.EPIC, "E")
    agent.propose_item(epic.id)
    human.approve_item(epic.id)
    assert "<button" not in client.get(f"/items/{epic.id}").text


# ------------------------------------------------------------------- actions


def test_approve_requires_valid_csrf_token(client: TestClient, agent: Service) -> None:
    seed(agent)
    assert client.post("/items/REQ-001/approve").status_code == 403
    wrong = client.post("/items/REQ-001/approve", data={"csrf_token": "nope"})
    assert wrong.status_code == 403
    assert agent.get_item("REQ-001").status is Status.PROPOSED


def test_human_approves_and_is_redirected(client: TestClient, agent: Service) -> None:
    seed(agent)
    response = post(client, "/items/REQ-001/approve")
    assert response.status_code == 303 and response.headers["location"] == "/items/REQ-001"  # type: ignore[attr-defined]
    assert agent.get_item("REQ-001").status is Status.APPROVED


def test_approve_from_dashboard_returns_home(client: TestClient, agent: Service) -> None:
    seed(agent)
    response = post(client, "/items/REQ-001/approve", next="home")
    assert response.headers["location"] == "/"  # type: ignore[attr-defined]


def test_redirect_target_cannot_be_chosen_by_the_form(client: TestClient, agent: Service) -> None:
    seed(agent)
    response = post(client, "/items/REQ-001/approve", next="https://evil.example/")
    assert response.headers["location"] == "/items/REQ-001"  # type: ignore[attr-defined]


def test_invalid_transition_shows_error_and_changes_nothing(
    client: TestClient, agent: Service
) -> None:
    seed(agent)  # REQ-002 is a draft: it cannot be approved yet.
    response = post(client, "/items/REQ-002/approve")
    assert response.status_code == 409  # type: ignore[attr-defined]
    assert "INVALID_TRANSITION" in response.text  # type: ignore[attr-defined]
    assert agent.get_item("REQ-002").status is Status.DRAFT


def test_full_lifecycle_through_the_ui(client: TestClient, agent: Service) -> None:
    seed(agent)
    post(client, "/items/REQ-002/propose")
    post(client, "/items/REQ-002/approve")
    post(client, "/items/REQ-002/implement")
    assert agent.get_item("REQ-002").status is Status.IMPLEMENTED


def test_unknown_action_and_unknown_item(client: TestClient, agent: Service) -> None:
    seed(agent)
    assert post(client, "/items/REQ-001/delete").status_code == 404  # type: ignore[attr-defined]
    assert post(client, "/items/REQ-099/approve").status_code == 404  # type: ignore[attr-defined]


def test_get_cannot_trigger_actions(client: TestClient, agent: Service) -> None:
    seed(agent)
    assert client.get("/items/REQ-001/approve").status_code == 405
    assert agent.get_item("REQ-001").status is Status.PROPOSED


# ------------------------------------------------------------------ security


def test_foreign_host_header_is_rejected(storage: Storage, agent: Service) -> None:
    seed(agent)
    app = create_app(storage, csrf_token=TOKEN)
    rebinding = TestClient(app, base_url="http://evil.example", follow_redirects=False)
    assert rebinding.get("/").status_code == 400
    assert rebinding.post(
        "/items/REQ-001/approve", data={"csrf_token": TOKEN}
    ).status_code == 400
    assert agent.get_item("REQ-001").status is Status.PROPOSED


def test_extra_allowed_hosts_are_honoured(storage: Storage) -> None:
    app = create_app(storage, allowed_hosts=["specs.internal"], csrf_token=TOKEN)
    ok = TestClient(app, base_url="http://specs.internal:8765")
    assert ok.get("/").status_code == 200
    assert TestClient(app, base_url="http://localhost").get("/").status_code == 400


def test_security_headers(client: TestClient) -> None:
    headers = client.get("/").headers
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    assert "script-src" not in headers["content-security-policy"]
    assert headers["x-frame-options"] == "DENY"
    assert headers["x-content-type-options"] == "nosniff"


def test_random_csrf_token_is_generated_per_app(storage: Storage) -> None:
    first = TestClient(create_app(storage), base_url="http://localhost").get("/")
    second = TestClient(create_app(storage), base_url="http://localhost").get("/")
    assert first.status_code == second.status_code == 200
