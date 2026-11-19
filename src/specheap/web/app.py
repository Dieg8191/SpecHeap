"""Web UI application.

Like the MCP server, this module is a thin adapter: every action goes through
``Service(actor=Actor.HUMAN)``, so the business rules are not duplicated here.

The UI is the only place where approval is available over a network interface, so it is
hardened even though it targets local use:

* The ``Host`` header is validated (blocks DNS-rebinding attacks from other websites).
* Every state-changing request needs a per-process CSRF token (blocks cross-site POSTs).
* Pages cannot be framed and may not load any script, image or remote resource.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response
from starlette.routing import Route
from starlette.templating import Jinja2Templates

from specheap.core.errors import SpecHeapError
from specheap.core.models import Actor, Item, ItemType, Status
from specheap.core.ports import Storage
from specheap.core.service import Service

TEMPLATES_DIR = Path(__file__).parent / "templates"
DEFAULT_ALLOWED_HOSTS = ("127.0.0.1", "localhost")

_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
    "base-uri 'none'; frame-ancestors 'none'"
)

# Error codes that map to something other than a generic 409 conflict.
_STATUS_FOR_CODE = {"NOT_FOUND": 404, "FORBIDDEN_FOR_AGENT": 403, "VALIDATION_ERROR": 400}


@dataclass
class Node:
    """An item with its children, used to render the tree."""

    item: Item
    badges: list[str] = field(default_factory=list)
    children: list[Node] = field(default_factory=list)


@dataclass(frozen=True)
class Action:
    """A lifecycle action a human can trigger from the UI."""

    slug: str
    label: str
    style: str
    run: Callable[[Service, str], Item]


ACTIONS: dict[str, Action] = {
    "propose": Action("propose", "Propose for review", "secondary", Service.propose_item),
    "approve": Action("approve", "Approve", "primary", Service.approve_item),
    "implement": Action(
        "implement", "Mark implemented", "secondary", lambda s, i: s.mark_implemented(i)
    ),
}


def actions_for(item: Item) -> list[Action]:
    """Actions that make sense for the item's current status."""
    if item.status is Status.DRAFT:
        return [ACTIONS["propose"]]
    if item.status in (Status.PROPOSED, Status.STALE):
        return [ACTIONS["approve"]]
    if item.status is Status.APPROVED and item.type in (ItemType.REQ, ItemType.SPEC):
        return [ACTIONS["implement"]]
    return []


class SecurityHeaders(BaseHTTPMiddleware):
    """Add defensive headers to every response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = _CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response


def create_app(
    storage: Storage,
    *,
    allowed_hosts: Sequence[str] = DEFAULT_ALLOWED_HOSTS,
    csrf_token: str | None = None,
) -> Starlette:
    """Build the ASGI application.

    Args:
        storage: where items live.
        allowed_hosts: accepted ``Host`` header values (ports are ignored).
        csrf_token: fixed token, for tests. By default a random one is generated per process.
    """
    service = Service(storage, Actor.HUMAN)
    token = csrf_token or secrets.token_urlsafe(32)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    def render(request: Request, name: str, status_code: int = 200, **context: Any) -> Response:
        context.setdefault("csrf_token", token)
        return templates.TemplateResponse(request, name, context, status_code=status_code)

    # ------------------------------------------------------------------ pages

    async def index(request: Request) -> Response:
        items = service.list_items()
        gaps = service.list_gaps()
        labels: dict[str, list[str]] = {}
        for item_id in gaps.reqs_without_spec:
            labels.setdefault(item_id, []).append("no spec")
        for item_id in (*gaps.reqs_without_verification, *gaps.specs_without_verification):
            labels.setdefault(item_id, []).append("no verification")
        for item_id in gaps.failed_verifications:
            labels.setdefault(item_id, []).append("failed")
        return render(
            request,
            "index.html",
            overview=service.get_overview(),
            review=[i for i in items if i.status in (Status.PROPOSED, Status.STALE)],
            gaps=gaps,
            roots=_build_tree(items, labels),
            actions_for=actions_for,
        )

    def item_page(
        request: Request,
        item_id: str,
        *,
        error: dict[str, Any] | None = None,
        status_code: int = 200,
    ) -> Response:
        try:
            context = service.get_context(item_id)
        except SpecHeapError as exc:
            return render(request, "not_found.html", 404, item_id=item_id, error=exc.to_dict())
        item = context.item
        children = service.list_items(parent_id=item_id)
        child_ids = {c.id for c in children}
        return render(
            request,
            "item.html",
            status_code,
            item=item,
            ancestors=context.ancestors,
            children=children,
            linked=[i for i in context.descendants if i.id not in child_ids],
            targets=[service.get_item(t) for t in (*item.satisfies, *item.verifies)],
            actions=actions_for(item),
            error=error,
        )

    async def item_detail(request: Request) -> Response:
        return item_page(request, request.path_params["item_id"])

    # ---------------------------------------------------------------- actions

    async def run_action(request: Request) -> Response:
        form = await request.form()
        submitted = str(form.get("csrf_token", ""))
        if not secrets.compare_digest(submitted.encode(), token.encode()):
            return PlainTextResponse("Invalid or missing CSRF token.", status_code=403)

        item_id: str = request.path_params["item_id"]
        action = ACTIONS.get(request.path_params["action"])
        if action is None:
            return PlainTextResponse("Unknown action.", status_code=404)
        try:
            action.run(service, item_id)
        except SpecHeapError as exc:
            status_code = _STATUS_FOR_CODE.get(exc.code, 409)
            return item_page(request, item_id, error=exc.to_dict(), status_code=status_code)
        # Only two fixed destinations are allowed, so the form cannot cause an open redirect.
        destination = "/" if form.get("next") == "home" else f"/items/{item_id}"
        return RedirectResponse(destination, status_code=303)

    return Starlette(
        routes=[
            Route("/", index),
            Route("/items/{item_id}", item_detail),
            Route("/items/{item_id}/{action}", run_action, methods=["POST"]),
        ],
        middleware=[
            Middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts)),
            Middleware(SecurityHeaders),
        ],
    )


def _build_tree(items: list[Item], labels: dict[str, list[str]]) -> list[Node]:
    """Nest items under their parents, preserving the order of ``items``."""
    nodes = {item.id: Node(item, labels.get(item.id, [])) for item in items}
    roots: list[Node] = []
    for item in items:
        parent = nodes.get(item.parent) if item.parent else None
        (parent.children if parent else roots).append(nodes[item.id])
    return roots
