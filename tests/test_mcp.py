"""Contract tests for the MCP server, driven through the SDK's in-memory client."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from mcp.client import Client

from specheap.core.models import Actor, ItemType
from specheap.core.ports import Storage
from specheap.core.service import Service
from specheap.mcp import build_server

READ_TOOLS = {
    "get_overview",
    "list_items",
    "get_item",
    "get_context",
    "trace",
    "list_gaps",
    "next_work",
}
WRITE_TOOLS = {
    "create_item",
    "update_item",
    "propose_item",
    "link_items",
    "unlink_items",
    "mark_implemented",
    "report_verification",
}


def run_with_client(
    storage: Storage, scenario: Callable[[Client], Awaitable[Any]], *, readonly: bool = False
) -> Any:
    server = build_server(Service(storage, Actor.AGENT, readonly=readonly))

    async def main() -> Any:
        async with Client(server) as client:
            return await scenario(client)

    return asyncio.run(main())


async def call(client: Client, name: str, **arguments: Any) -> dict[str, Any]:
    result = await client.call_tool(name, arguments)
    assert not result.is_error, result
    assert result.structured_content is not None
    return result.structured_content


async def call_error(client: Client, name: str, **arguments: Any) -> dict[str, Any]:
    result = await client.call_tool(name, arguments)
    assert result.is_error, result
    text = result.content[0].text  # type: ignore[union-attr]
    return json.loads(text[text.index("{") :])


def test_server_requires_agent_actor(storage: Storage) -> None:
    with pytest.raises(ValueError):
        build_server(Service(storage, Actor.HUMAN))


def test_tool_surface_never_includes_approval(storage: Storage) -> None:
    async def scenario(client: Client) -> set[str]:
        return {tool.name for tool in (await client.list_tools()).tools}

    names = run_with_client(storage, scenario)
    assert names == READ_TOOLS | WRITE_TOOLS
    assert not any("approve" in name for name in names)


def test_readonly_exposes_only_read_tools(storage: Storage) -> None:
    async def scenario(client: Client) -> tuple[set[str], dict[str, Any]]:
        names = {tool.name for tool in (await client.list_tools()).tools}
        result = await client.call_tool("create_item", {"item_type": "epic", "title": "x"})
        return names, {"is_error": result.is_error}

    names, outcome = run_with_client(storage, scenario, readonly=True)
    assert names == READ_TOOLS
    assert outcome["is_error"]


def test_agent_workflow_end_to_end(storage: Storage) -> None:
    async def scenario(client: Client) -> dict[str, Any]:
        epic = await call(client, "create_item", item_type="epic", title="Auth")
        feat = await call(
            client, "create_item", item_type="feature", title="Login", parent_id=epic["id"]
        )
        req = await call(
            client, "create_item", item_type="req", title="Lockout", parent_id=feat["id"],
            body="WHEN 3 failures, THE SYSTEM SHALL lock.",
        )
        spec = await call(client, "create_item", item_type="spec", title="Counter",
                          parent_id=req["id"])
        ver = await call(client, "create_item", item_type="verification", title="Lock test",
                         parent_id=req["id"])
        proposed = await call(client, "propose_item", item_id=req["id"])
        gaps_before = await call(client, "list_gaps", scope_id=feat["id"])
        ctx = await call(client, "get_context", item_id=feat["id"])
        edited = await call(client, "update_item", item_id=req["id"],
                            expected_revision=proposed["revision"], title="Lockout v2")
        conflict = await call_error(client, "update_item", item_id=req["id"],
                                    expected_revision=proposed["revision"], title="Again")
        failing = await call(client, "report_verification", item_id=ver["id"], result="fail",
                             evidence="ci", run_ref="run-1")
        return {
            "ids": [epic["id"], feat["id"], req["id"], spec["id"], ver["id"]],
            "proposed": proposed,
            "gaps": gaps_before,
            "ctx": ctx,
            "edited": edited,
            "conflict": conflict,
            "failing": failing,
        }

    out = run_with_client(storage, scenario)
    assert out["ids"] == ["EPIC-001", "FEAT-001", "REQ-001", "SPEC-001", "VER-001"]
    assert out["proposed"]["status"] == "proposed"
    assert out["proposed"]["revision"]
    assert out["gaps"]["specs_without_verification"] == ["SPEC-001"]
    assert [i["id"] for i in out["ctx"]["ancestors"]] == ["EPIC-001"]
    assert {i["id"] for i in out["ctx"]["descendants"]} == {"REQ-001", "SPEC-001", "VER-001"}
    assert out["edited"]["title"] == "Lockout v2"
    assert out["conflict"]["code"] == "REVISION_CONFLICT"
    assert out["conflict"]["hint"]
    assert out["failing"]["result"] == "fail"


def test_agent_cannot_reach_approved_state(storage: Storage) -> None:
    """Even after proposing, nothing the agent can call moves an item to approved."""

    async def scenario(client: Client) -> tuple[dict[str, Any], dict[str, Any]]:
        epic = await call(client, "create_item", item_type="epic", title="E")
        proposed = await call(client, "propose_item", item_id=epic["id"])
        impl = await call_error(client, "mark_implemented", item_id=epic["id"])
        return proposed, impl

    proposed, impl = run_with_client(storage, scenario)
    assert proposed["status"] == "proposed"
    assert impl["code"] == "VALIDATION_ERROR"


def test_structured_errors_have_code_and_hint(storage: Storage) -> None:
    async def scenario(client: Client) -> list[dict[str, Any]]:
        return [
            await call_error(client, "get_item", item_id="REQ-404"),
            await call_error(client, "create_item", item_type="req", title="Orphan"),
            await call_error(client, "update_item", item_id="REQ-404", expected_revision="x"),
        ]

    not_found, bad_parent, update_nothing = run_with_client(storage, scenario)
    assert not_found["code"] == "NOT_FOUND" and not_found["hint"]
    assert bad_parent["code"] == "INVALID_PARENT"
    assert update_nothing["code"] == "VALIDATION_ERROR"


def test_list_items_pagination(storage: Storage) -> None:
    service = Service(storage, Actor.AGENT)
    for n in range(5):
        service.create_item(ItemType.EPIC, f"Epic {n}")

    async def scenario(client: Client) -> list[dict[str, Any]]:
        first = await call(client, "list_items", limit=2)
        second = await call(client, "list_items", limit=2, cursor=first["next_cursor"])
        last = await call(client, "list_items", limit=2, cursor=second["next_cursor"])
        bad = await call_error(client, "list_items", cursor="abc")
        return [first, second, last, bad]

    first, second, last, bad = run_with_client(storage, scenario)
    assert [i["id"] for i in first["items"]] == ["EPIC-001", "EPIC-002"]
    assert [i["id"] for i in second["items"]] == ["EPIC-003", "EPIC-004"]
    assert [i["id"] for i in last["items"]] == ["EPIC-005"]
    assert first["total"] == 5 and last["next_cursor"] is None
    assert bad["code"] == "VALIDATION_ERROR"


def test_resources_and_prompts(storage: Storage) -> None:
    service = Service(storage, Actor.AGENT)
    epic = service.create_item(ItemType.EPIC, "Auth", body="Users can sign in.")
    feat = service.create_item(ItemType.FEATURE, "Login", parent_id=epic.id)

    async def scenario(client: Client) -> dict[str, Any]:
        overview = await client.read_resource("specheap://overview")
        item = await client.read_resource(f"specheap://epic/{epic.id}")
        context = await client.read_resource(f"specheap://feature/{feat.id}/context")
        prompts = await client.list_prompts()
        prompt = await client.get_prompt("decompose_feature", {"feature_id": feat.id})
        return {
            "overview": overview.contents[0].text,  # type: ignore[union-attr]
            "item": item.contents[0].text,  # type: ignore[union-attr]
            "context": context.contents[0].text,  # type: ignore[union-attr]
            "prompts": {p.name for p in prompts.prompts},
            "prompt_text": prompt.messages[0].content.text,  # type: ignore[union-attr]
        }

    out = run_with_client(storage, scenario)
    assert json.loads(out["overview"])["total_items"] == 2
    assert out["item"].startswith("# EPIC-001: Auth") and "Users can sign in." in out["item"]
    assert json.loads(out["context"])["ancestors"][0]["id"] == "EPIC-001"
    assert out["prompts"] == {
        "decompose_feature",
        "draft_specs",
        "plan_verifications",
        "review_gaps",
    }
    assert "FEAT-001" in out["prompt_text"]
