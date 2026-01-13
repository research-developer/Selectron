"""
Subdomain Extraction Middleware

Extracts the application name from the subdomain of incoming requests.
Since Sanic does not support wildcard subdomain patterns natively,
this middleware parses the Host header to extract the subdomain.

URL Pattern:
    {app}.pom.localhost:8000/{path}

Examples:
    claude.pom.localhost:8000/pom/elements -> app = "claude"
    obsidian.pom.localhost:8000/dom/click  -> app = "obsidian"
    pom.localhost:8000/health              -> app = None (no subdomain)
"""

from typing import Optional
from sanic import Request
from sanic.exceptions import BadRequest

from ..config import get_server_config


def extract_subdomain(request: Request) -> Optional[str]:
    """
    Extract the subdomain (app name) from the request Host header.

    Args:
        request: Sanic request object

    Returns:
        The subdomain/app name, or None if not present

    Examples:
        >>> # Host: claude.pom.localhost:8000
        >>> extract_subdomain(request)
        'claude'

        >>> # Host: pom.localhost:8000
        >>> extract_subdomain(request)
        None
    """
    # Get host without port
    host = request.host.split(":")[0]
    parts = host.split(".")

    # Check for development header override
    if "X-Selectron-App" in request.headers:
        return request.headers["X-Selectron-App"]

    # Expected format: {app}.{domain}
    # e.g., claude.pom.localhost -> ["claude", "pom", "localhost"]
    config = get_server_config()
    domain_parts = config.domain.split(".")

    # If host has more parts than the base domain, extract subdomain
    if len(parts) > len(domain_parts):
        subdomain = parts[0]
        # Validate the rest matches the expected domain
        remaining = ".".join(parts[1:])
        if remaining == config.domain:
            return subdomain

    return None


class SubdomainMiddleware:
    """
    Middleware class for subdomain extraction.

    Attaches the following to request.ctx:
        - app: The application name from subdomain
        - app_required: Whether the current route requires an app

    Usage:
        app = Sanic("SelectronServer")
        SubdomainMiddleware.attach(app)
    """

    # Routes that don't require an app subdomain
    APP_OPTIONAL_PATHS = frozenset({
        "/",
        "/health",
        "/apps",
        "/docs",
    })

    @classmethod
    def attach(cls, app):
        """Attach the middleware to a Sanic app."""

        @app.middleware("request")
        async def subdomain_middleware(request: Request):
            """Extract subdomain and attach to request context."""
            # Extract app from subdomain
            app_name = extract_subdomain(request)
            request.ctx.app = app_name

            # Check if this route requires an app
            path = request.path.rstrip("/")
            request.ctx.app_required = path not in cls.APP_OPTIONAL_PATHS

            # For routes that require an app, validate early
            if request.ctx.app_required and not app_name:
                # Check if this is a root path that might not need app
                path_parts = path.strip("/").split("/")
                if path_parts and path_parts[0] in get_server_config().valid_roots:
                    raise BadRequest(
                        f"Application subdomain required. "
                        f"Use: {{app}}.{get_server_config().domain}{request.path}"
                    )

        return subdomain_middleware


def get_app_from_request(request: Request) -> str:
    """
    Get the app name from the request, raising if not present.

    Args:
        request: Sanic request with ctx.app set by middleware

    Returns:
        The application name

    Raises:
        BadRequest: If no app is available
    """
    if not hasattr(request.ctx, "app") or not request.ctx.app:
        config = get_server_config()
        raise BadRequest(
            f"Application subdomain required. "
            f"Use: {{app}}.{config.domain}{request.path}"
        )
    return request.ctx.app
