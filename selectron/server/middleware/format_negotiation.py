"""
Format Negotiation Middleware

Handles response format selection based on:
1. URL suffix (e.g., .json, .html, .xml)
2. Accept header content negotiation
3. Query parameter (?format=json)
4. Default format fallback

WebSpec Format Suffix Rule:
    The suffix determines response format and is stripped from the path
    for routing purposes.
"""

import re
from typing import Optional, Tuple
from sanic import Request
from sanic.exceptions import BadRequest

from ..config import get_server_config, DEFAULT_FORMAT


# Pattern to extract format suffix from path
FORMAT_SUFFIX_PATTERN = re.compile(r"\.([a-z]+)$", re.IGNORECASE)

# Content-Type mappings
FORMAT_CONTENT_TYPES = {
    "json": "application/json",
    "html": "text/html",
    "xml": "application/xml",
    "yaml": "application/x-yaml",
}

# Accept header to format mapping
ACCEPT_TO_FORMAT = {
    "application/json": "json",
    "text/html": "html",
    "application/xml": "xml",
    "text/xml": "xml",
    "application/x-yaml": "yaml",
    "text/yaml": "yaml",
}


def parse_path_format(path: str) -> Tuple[str, Optional[str]]:
    """
    Parse a path to extract the format suffix.

    Args:
        path: Request path (e.g., /pom/elements/btn.json)

    Returns:
        Tuple of (clean_path, format) where format may be None

    Examples:
        >>> parse_path_format("/pom/elements/btn.json")
        ('/pom/elements/btn', 'json')

        >>> parse_path_format("/pom/elements/btn")
        ('/pom/elements/btn', None)
    """
    match = FORMAT_SUFFIX_PATTERN.search(path)
    if match:
        fmt = match.group(1).lower()
        clean_path = path[:match.start()]
        return clean_path, fmt
    return path, None


def strip_format_suffix(value: str) -> Tuple[str, Optional[str]]:
    """
    Strip format suffix from a value (e.g., element ID).

    Args:
        value: Value that may have format suffix (e.g., "btn.json")

    Returns:
        Tuple of (clean_value, format) where format may be None

    Examples:
        >>> strip_format_suffix("btn.json")
        ('btn', 'json')

        >>> strip_format_suffix("my-element")
        ('my-element', None)
    """
    match = FORMAT_SUFFIX_PATTERN.search(value)
    if match:
        fmt = match.group(1).lower()
        config = get_server_config()
        if config.is_valid_format(fmt):
            clean_value = value[:match.start()]
            return clean_value, fmt
    return value, None


def negotiate_format(request: Request) -> str:
    """
    Determine the response format from the request.

    Priority:
        1. URL suffix (.json, .html, etc.)
        2. Query parameter (?format=json)
        3. Accept header
        4. Default format

    Args:
        request: Sanic request object

    Returns:
        Format string (e.g., "json", "html")

    Raises:
        BadRequest: If requested format is not supported
    """
    config = get_server_config()

    # 1. Check URL suffix (already parsed by middleware)
    if hasattr(request.ctx, "format") and request.ctx.format:
        fmt = request.ctx.format
        if config.is_valid_format(fmt):
            return fmt
        raise BadRequest(f"Unsupported format: {fmt}")

    # 2. Check query parameter
    if fmt := request.args.get("format"):
        fmt = fmt.lower()
        if config.is_valid_format(fmt):
            return fmt
        raise BadRequest(f"Unsupported format: {fmt}")

    # 3. Check Accept header
    accept = request.headers.get("Accept", "")
    for content_type, fmt in ACCEPT_TO_FORMAT.items():
        if content_type in accept:
            if config.is_valid_format(fmt):
                return fmt

    # 4. Default format
    return config.default_format


def get_content_type(fmt: str) -> str:
    """
    Get the Content-Type header value for a format.

    Args:
        fmt: Format string (e.g., "json")

    Returns:
        Content-Type value (e.g., "application/json")
    """
    return FORMAT_CONTENT_TYPES.get(fmt, "application/octet-stream")


class FormatMiddleware:
    """
    Middleware class for format negotiation.

    Attaches the following to request.ctx:
        - format: The negotiated response format
        - clean_path: Path with format suffix removed

    Usage:
        app = Sanic("SelectronServer")
        FormatMiddleware.attach(app)
    """

    @classmethod
    def attach(cls, app):
        """Attach the middleware to a Sanic app."""

        @app.middleware("request")
        async def format_middleware(request: Request):
            """Parse format from path and negotiate."""
            # Parse format suffix from path
            clean_path, path_format = parse_path_format(request.path)
            request.ctx.clean_path = clean_path
            request.ctx.path_format = path_format

            # Store format from suffix (will be used by negotiate_format)
            request.ctx.format = path_format

        @app.middleware("response")
        async def format_response_middleware(request: Request, response):
            """Set Content-Type based on negotiated format."""
            if hasattr(request.ctx, "format") and request.ctx.format:
                content_type = get_content_type(request.ctx.format)
                response.content_type = content_type
            return response

        return format_middleware
