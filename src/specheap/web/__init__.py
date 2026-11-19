"""Web interface: a JSON API over the core ``Service`` plus the compiled React frontend."""

from specheap.web.app import DEFAULT_ALLOWED_HOSTS, STATIC_DIR, create_app, frontend_built

__all__ = ["DEFAULT_ALLOWED_HOSTS", "STATIC_DIR", "create_app", "frontend_built"]
