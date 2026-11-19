"""Tests for the web API, its security boundary and static hosting."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from specheap.core.models import Actor, ItemType, Status, VerificationResult
from specheap.core.ports import Storage
from specheap.core.service import Service
from specheap.web import create_app, frontend_built

TOKEN = "test-token"
CSRF = {"X-CSRF-Token": TOKEN}


@pytest.fixture
def agent(storage: Storage) -> Service:
    return Service(storage, Actor.AGENT)


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "static"
    (directory / "assets").mkdir(parents=True)
    index = "<!doctype html><title>SpecHeap</title>"
    (directory / "index.html").write_text(index, encoding="utf-8")
    (directory / "assets" / "app.js").write_text("console.log('app')", encoding="utf-8")
    return directory


@pytest.fixture
def client(storage: Storage, static_dir: Path) -> TestClient:
    app = create_app(storage, csrf_token=TOKEN, static_dir=static_dir)
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


def act(client: TestClient, item_id: str, action: str, headers: dict[str, str] | None = None):
    return client.post(
        f"/api/items/{item_id}/actions/{action}", headers=CSRF if headers is None else headers
    )


# --------------------------------------------------------------------- reading


def test_session_returns_csrf_token(client: TestClient) -> None:
    assert client.get("/api/session").json() == {"csrf_token": TOKEN}


def test_empty_dashboard(client: TestClient) -> None:
    data = client.get("/api/dashboard").json()
    assert data["items"] == []
    assert data["overview"]["total_items"] == 0 and data["overview"]["coverage_percent"] == 100.0


def test_dashboard_contents(client: TestClient, agent: Service) -> None:
    seed(agent)
    data = client.get("/api/dashboard").json()
    assert data["overview"]["total_items"] == 6
    assert [i["id"] for i in data["items"]][:3] == ["EPIC-001", "FEAT-001", "REQ-001"]
    assert data["gaps"]["reqs_without_spec"] == ["REQ-002"]
    assert data["items"][2]["revision"]
    assert {"id", "type", "title", "status", "parent", "body"} <= data["items"][0].keys()


def test_item_detail(client: TestClient, agent: Service) -> None:
    seed(agent)
    data = client.get("/api/items/REQ-001").json()
    assert data["item"]["title"] == "Lock after failures"
    assert [a["id"] for a in data["ancestors"]] == ["EPIC-001", "FEAT-001"]
    assert [c["id"] for c in data["children"]] == ["SPEC-001", "VER-001"]
    assert data["downstream"] == [] and data["targets"] == []
    assert data["actions"] == [{"slug": "approve", "label": "Approve", "style": "primary"}]


def test_downstream_excludes_direct_children(client: TestClient, agent: Service) -> None:
    seed(agent)
    agent.create_item(ItemType.VERIFICATION, "Counter test", parent_id="SPEC-001")
    data = client.get("/api/items/REQ-001").json()
    assert [d["id"] for d in data["downstream"]] == ["VER-002"]


def test_verification_detail_carries_result(client: TestClient, agent: Service) -> None:
    seed(agent)
    agent.report_verification("VER-001", VerificationResult.FAIL, evidence="boom", run_ref="run-7")
    item = client.get("/api/items/VER-001").json()["item"]
    assert (item["result"], item["evidence"], item["run_ref"]) == ("fail", "boom", "run-7")


def test_unknown_and_malformed_items_return_structured_404(client: TestClient) -> None:
    missing = client.get("/api/items/REQ-099")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND" and missing.json()["error"]["hint"]
    malformed = client.get("/api/items/nope")
    assert malformed.status_code == 400
    assert malformed.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unknown_api_route_is_json_404(client: TestClient) -> None:
    response = client.get("/api/nothing/here")
    assert response.status_code == 404 and response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (Status.DRAFT, ["propose"]),
        (Status.PROPOSED, ["approve"]),
        (Status.APPROVED, ["implement"]),
    ],
)
def test_available_actions_follow_status(
    client: TestClient, agent: Service, status: Status, expected: list[str]
) -> None:
    human = Service(agent._storage, Actor.HUMAN)  # noqa: SLF001
    epic = agent.create_item(ItemType.EPIC, "E")
    feat = agent.create_item(ItemType.FEATURE, "F", parent_id=epic.id)
    req = agent.create_item(ItemType.REQ, "R", parent_id=feat.id)
    if status in (Status.PROPOSED, Status.APPROVED):
        agent.propose_item(req.id)
    if status is Status.APPROVED:
        human.approve_item(req.id)
    actions = client.get(f"/api/items/{req.id}").json()["actions"]
    assert [a["slug"] for a in actions] == expected


def test_no_actions_on_approved_epic(client: TestClient, agent: Service) -> None:
    human = Service(agent._storage, Actor.HUMAN)  # noqa: SLF001
    epic = agent.create_item(ItemType.EPIC, "E")
    agent.propose_item(epic.id)
    human.approve_item(epic.id)
    assert client.get(f"/api/items/{epic.id}").json()["actions"] == []


# --------------------------------------------------------------------- actions


def test_human_approves_and_response_reflects_new_state(
    client: TestClient, agent: Service
) -> None:
    seed(agent)
    response = act(client, "REQ-001", "approve")
    assert response.status_code == 200
    body = response.json()
    assert body["item"]["status"] == "approved"
    assert [a["slug"] for a in body["actions"]] == ["implement"]
    assert agent.get_item("REQ-001").status is Status.APPROVED


def test_full_lifecycle(client: TestClient, agent: Service) -> None:
    seed(agent)
    for action in ("propose", "approve", "implement"):
        assert act(client, "REQ-002", action).status_code == 200
    assert agent.get_item("REQ-002").status is Status.IMPLEMENTED


def test_invalid_transition_is_a_409_and_changes_nothing(
    client: TestClient, agent: Service
) -> None:
    seed(agent)  # REQ-002 is still a draft.
    response = act(client, "REQ-002", "approve")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_TRANSITION"
    assert agent.get_item("REQ-002").status is Status.DRAFT


def test_unknown_action_and_unknown_item(client: TestClient, agent: Service) -> None:
    seed(agent)
    assert act(client, "REQ-001", "delete").status_code == 404
    assert act(client, "REQ-001", "delete").json()["error"]["code"] == "UNKNOWN_ACTION"
    assert act(client, "REQ-099", "approve").status_code == 404


def test_get_cannot_trigger_actions(client: TestClient, agent: Service) -> None:
    seed(agent)
    assert client.get("/api/items/REQ-001/actions/approve").status_code in (404, 405)
    assert agent.get_item("REQ-001").status is Status.PROPOSED


# -------------------------------------------------------------------- security


@pytest.mark.parametrize("headers", [{}, {"X-CSRF-Token": "wrong"}, {"X-CSRF-Token": ""}])
def test_actions_require_the_csrf_token(
    client: TestClient, agent: Service, headers: dict[str, str]
) -> None:
    seed(agent)
    response = act(client, "REQ-001", "approve", headers=headers)
    assert response.status_code == 403 and response.json()["error"]["code"] == "CSRF_INVALID"
    assert agent.get_item("REQ-001").status is Status.PROPOSED


def test_form_posts_without_the_header_cannot_approve(client: TestClient, agent: Service) -> None:
    """A classic cross-site form submission cannot set custom headers."""
    seed(agent)
    response = client.post("/api/items/REQ-001/actions/approve", data={"csrf_token": TOKEN})
    assert response.status_code == 403
    assert agent.get_item("REQ-001").status is Status.PROPOSED


def test_foreign_host_header_is_rejected(
    storage: Storage, agent: Service, static_dir: Path
) -> None:
    seed(agent)
    app = create_app(storage, csrf_token=TOKEN, static_dir=static_dir)
    rebinding = TestClient(app, base_url="http://evil.example", follow_redirects=False)
    assert rebinding.get("/api/dashboard").status_code == 400
    assert rebinding.post("/api/items/REQ-001/actions/approve", headers=CSRF).status_code == 400
    assert agent.get_item("REQ-001").status is Status.PROPOSED


def test_extra_allowed_hosts_are_honoured(storage: Storage, static_dir: Path) -> None:
    app = create_app(storage, allowed_hosts=["specs.internal"], static_dir=static_dir)
    allowed = TestClient(app, base_url="http://specs.internal:8765")
    assert allowed.get("/api/session").status_code == 200
    assert TestClient(app, base_url="http://localhost").get("/api/session").status_code == 400


def test_security_headers(client: TestClient) -> None:
    headers = client.get("/api/dashboard").headers
    csp = headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp and "script-src 'self'" in csp
    assert "unsafe-eval" not in csp and "script-src 'self' 'unsafe-inline'" not in csp
    assert headers["x-frame-options"] == "DENY"
    assert headers["x-content-type-options"] == "nosniff"


def test_random_csrf_token_differs_per_app(storage: Storage, static_dir: Path) -> None:
    def token() -> str:
        app = create_app(storage, static_dir=static_dir)
        return TestClient(app, base_url="http://localhost").get("/api/session").json()["csrf_token"]

    first, second = token(), token()
    assert first != second and len(first) >= 32


# --------------------------------------------------------------- static hosting


def test_serves_index_and_assets(client: TestClient) -> None:
    assert "<title>SpecHeap</title>" in client.get("/").text
    assert "console.log" in client.get("/assets/app.js").text


def test_client_side_routes_fall_back_to_index(client: TestClient) -> None:
    response = client.get("/items/REQ-001")
    assert response.status_code == 200 and "<title>SpecHeap</title>" in response.text
    assert response.headers["cache-control"] == "no-cache"


def test_static_hosting_blocks_path_traversal(
    storage: Storage, static_dir: Path, tmp_path: Path
) -> None:
    (tmp_path / "secret.txt").write_text("TOP SECRET", encoding="utf-8")
    app = create_app(storage, static_dir=static_dir)
    client = TestClient(app, base_url="http://localhost")
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"):
        assert "TOP SECRET" not in client.get(path).text


def test_missing_frontend_explains_how_to_build_it(storage: Storage, tmp_path: Path) -> None:
    empty = tmp_path / "nothing"
    assert not frontend_built(empty)
    client = TestClient(create_app(storage, static_dir=empty), base_url="http://localhost")
    response = client.get("/")
    assert response.status_code == 503 and "npm run build" in response.text
    assert client.get("/api/session").status_code == 200  # The API still works.
