"""Local web UI: a server-rendered adapter over the core ``Service``."""

from specheap.web.app import DEFAULT_ALLOWED_HOSTS, create_app

__all__ = ["DEFAULT_ALLOWED_HOSTS", "create_app"]
