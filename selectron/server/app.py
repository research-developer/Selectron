"""
Selectron WebSpec Server

Main Sanic application factory implementing the WebSpec URL grammar.

Usage:
    from selectron.server import create_app

    app = create_app()
    app.run(host="0.0.0.0", port=8000)

    # Or with config override:
    from selectron.server.config import ServerConfig
    config = ServerConfig(port=9000)
    app = create_app(config)
"""

from typing import Optional
from sanic import Sanic, Request
from sanic.response import json as json_response

from .config import ServerConfig, get_server_config, set_server_config
from .middleware import SubdomainMiddleware, FormatMiddleware
from .routes import pom_bp, dom_bp, wim_bp


def create_app(config: Optional[ServerConfig] = None) -> Sanic:
    """
    Create and configure the Selectron WebSpec server.

    Args:
        config: Optional server configuration (uses environment if not provided)

    Returns:
        Configured Sanic application
    """
    # Set config if provided
    if config:
        set_server_config(config)
    else:
        config = get_server_config()

    # Create Sanic app
    app = Sanic("SelectronWebSpec")

    # Configure based on settings
    app.config.FALLBACK_ERROR_FORMAT = "json"

    # Attach middleware
    SubdomainMiddleware.attach(app)
    FormatMiddleware.attach(app)

    # Register blueprints for each path root
    app.blueprint(pom_bp)
    app.blueprint(dom_bp)
    app.blueprint(wim_bp)

    # Root endpoints (no app required)
    @app.get("/")
    async def index(request: Request):
        """Server info and available endpoints."""
        return json_response({
            "name": "Selectron WebSpec Server",
            "version": "0.1.0",
            "roots": list(config.valid_roots),
            "formats": list(config.supported_formats),
            "usage": f"{{app}}.{config.domain}/{{root}}/{{collection}}/{{id}}{{.format}}",
            "examples": [
                f"claude.{config.domain}/pom/elements",
                f"obsidian.{config.domain}/pom/operations/open_file",
                f"cursor.{config.domain}/dom/elements/ref_1/click",
            ]
        })

    @app.get("/health")
    async def health(request: Request):
        """Health check endpoint."""
        return json_response({
            "status": "healthy",
            "app": getattr(request.ctx, "app", None),
        })

    @app.get("/apps")
    async def list_apps(request: Request):
        """
        List available applications with POMs.

        Returns apps that have POM definitions in the poms directory.
        """
        poms_dir = config.poms_dir
        apps = []

        if poms_dir.exists():
            for app_dir in poms_dir.iterdir():
                if app_dir.is_dir() and not app_dir.name.startswith("."):
                    # Check for elements.json or any POM file
                    elements_file = app_dir / "elements.json"
                    apps.append({
                        "name": app_dir.name,
                        "has_elements": elements_file.exists(),
                        "url": f"{app_dir.name}.{config.domain}",
                    })

        return json_response({
            "apps": apps,
            "poms_dir": str(poms_dir),
        })

    # Error handlers
    @app.exception(Exception)
    async def handle_exception(request: Request, exception: Exception):
        """Global exception handler."""
        status = getattr(exception, "status_code", 500)
        message = str(exception) if config.debug else "Internal server error"

        return json_response(
            {
                "error": type(exception).__name__,
                "message": message,
                "path": request.path,
                "app": getattr(request.ctx, "app", None),
            },
            status=status
        )

    return app


def run_server(
    host: Optional[str] = None,
    port: Optional[int] = None,
    debug: bool = False,
    auto_reload: bool = False,
):
    """
    Convenience function to run the server.

    Args:
        host: Host to bind to (default from config)
        port: Port to bind to (default from config)
        debug: Enable debug mode
        auto_reload: Enable auto-reload on code changes
    """
    config = get_server_config()
    app = create_app(config)

    app.run(
        host=host or config.host,
        port=port or config.port,
        debug=debug or config.debug,
        auto_reload=auto_reload,
    )


if __name__ == "__main__":
    run_server(debug=True, auto_reload=True)
