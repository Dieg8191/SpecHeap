"""Web application: JSON API and static hosting of the compiled frontend.

Like the MCP server, this module is a thin adapter: every action goes through
``Service(actor=Actor.HUMAN)``, so business rules are not duplicated here.

The API is the only network interface where approval is available, so it is hardened even
though it targets local use:

* The ``Host`` header is validated (blocks DNS-rebinding from other websites).
* State-changing requests need a per-process CSRF token sent in a custom header, which also
  forces a CORS preflight that this server never grants (blocks cross-site requests).
* Pages cannot be framed, and scripts may only come from the app itself.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

from specheap.core.errors import SpecHeapError
from specheap.core.models import Actor, Item, ItemType, Status
from specheap.core.ports import Storage
from specheap.core.schemas import ItemDTO, to_dtos
from specheap.core.service import Gaps, Overview, Service

STATIC_DIR = Path(__file__).parent / "static"
DEFAULT_ALLOWED_HOSTS = ("127.0.0.1", "localhost")
CSRF_HEADER = "x-csrf-token"

_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self' data:; connect-src 'self'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)

FRONTEND_MISSING = (
    "The SpecHeap frontend has not been built.\n"
    "Run `npm install && npm run build` inside the frontend/ directory, "
    "or use the Vite dev server (`npm run dev`), which proxies /api to this server.\n"
)

# Error codes that map to something other than a generic 409 conflict.
_STATUS_FOR_CODE = {"NOT_FOUND": 404, "FORBIDDEN_FOR_AGENT": 403, "VALIDATION_ERROR": 400}


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


# ------------------------------------------------------------------- API models


class ActionView(BaseModel):
    slug: str
    label: str
    style: str


class Dashboard(BaseModel):
    """Everything the overview page needs in one round trip."""

    overview: Overview
    gaps: Gaps
    items: list[ItemDTO]


class ItemDetail(BaseModel):
    """An item with the surrounding graph and the actions available to a human."""

    item: ItemDTO
    ancestors: list[ItemDTO]
    children: list[ItemDTO]
    downstream: list[ItemDTO]
    targets: list[ItemDTO]
    actions: list[ActionView]


# --------------------------------------------------------------------- plumbing


class SecurityHeaders(BaseHTTPMiddleware):
    """Add defensive headers to every response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = _CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response


def frontend_built(static_dir: Path = STATIC_DIR) -> bool:
    """Whether the compiled frontend is available."""
    return (static_dir / "index.html").is_file()


def _json(model: BaseModel, status_code: int = 200) -> JSONResponse:
    return JSONResponse(model.model_dump(mode="json"), status_code=status_code)


def _error(code: str, message: str, status_code: int, **extra: Any) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, **extra}}, status_code)


def _domain_error(exc: SpecHeapError) -> JSONResponse:
    return JSONResponse({"error": exc.to_dict()}, _STATUS_FOR_CODE.get(exc.code, 409))


def create_app(
    storage: Storage,
    *,
    allowed_hosts: Sequence[str] = DEFAULT_ALLOWED_HOSTS,
    csrf_token: str | None = None,
    static_dir: Path = STATIC_DIR,
) -> Starlette:
    """Build the ASGI application.

    Args:
        storage: where items live.
        allowed_hosts: accepted ``Host`` header values (ports are ignored).
        csrf_token: fixed token, for tests. By default a random one is generated per process.
        static_dir: directory with the compiled frontend.
    """
    service = Service(storage, Actor.HUMAN)
    token = csrf_token or secrets.token_urlsafe(32)
    root = static_dir.resolve()

    def detail(item_id: str) -> ItemDetail:
        context = service.get_context(item_id)
        children = service.list_items(parent_id=item_id)
        child_ids = {c.id for c in children}
        item = context.item
        return ItemDetail(
            item=ItemDTO.from_item(item),
            ancestors=to_dtos(context.ancestors),
            children=to_dtos(children),
            downstream=to_dtos([i for i in context.descendants if i.id not in child_ids]),
            targets=to_dtos([service.get_item(t) for t in (*item.satisfies, *item.verifies)]),
            actions=[
                ActionView(slug=a.slug, label=a.label, style=a.style) for a in actions_for(item)
            ],
        )

    async def session(request: Request) -> Response:
        return JSONResponse({"csrf_token": token})

    async def dashboard(request: Request) -> Response:
        return _json(
            Dashboard(
                overview=service.get_overview(),
                gaps=service.list_gaps(),
                items=to_dtos(service.list_items()),
            )
        )

    async def item_detail(request: Request) -> Response:
        try:
            return _json(detail(request.path_params["item_id"]))
        except SpecHeapError as exc:
            return _domain_error(exc)

    async def run_action(request: Request) -> Response:
        submitted = request.headers.get(CSRF_HEADER, "")
        if not secrets.compare_digest(submitted.encode(), token.encode()):
            return _error(
                "CSRF_INVALID",
                "Missing or invalid CSRF token.",
                403,
                hint="Reload the page to obtain a fresh token.",
            )
        action = ACTIONS.get(request.path_params["action"])
        if action is None:
            return _error(
                "UNKNOWN_ACTION", "Unknown action.", 404, hint=f"Use: {', '.join(ACTIONS)}."
            )
        item_id: str = request.path_params["item_id"]
        try:
            action.run(service, item_id)
            return _json(detail(item_id))
        except SpecHeapError as exc:
            return _domain_error(exc)

    async def api_not_found(request: Request) -> Response:
        return _error("NOT_FOUND", "Unknown API endpoint.", 404)

    async def frontend(request: Request) -> Response:
        index = root / "index.html"
        if not index.is_file():
            return PlainTextResponse(FRONTEND_MISSING, status_code=503)
        requested = request.path_params["path"]
        candidate = (root / requested).resolve()
        if requested and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        # Client-side routes fall back to the single-page app.
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return Starlette(
        routes=[
            Route("/api/session", session),
            Route("/api/dashboard", dashboard),
            Route("/api/items/{item_id}", item_detail),
            Route("/api/items/{item_id}/actions/{action}", run_action, methods=["POST"]),
            Route("/api/{rest:path}", api_not_found, methods=["GET", "POST"]),
            Route("/{path:path}", frontend),
        ],
        middleware=[
            Middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts)),
            Middleware(SecurityHeaders),
        ],
    )
