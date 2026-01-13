"""
Selectron Server Middleware

Request processing middleware for:
- Subdomain extraction (app identification)
- Format negotiation (response format handling)
- Git context (branch/worktree resolution)
"""

from .subdomain import extract_subdomain, SubdomainMiddleware
from .format_negotiation import negotiate_format, FormatMiddleware, strip_format_suffix

__all__ = [
    "extract_subdomain",
    "SubdomainMiddleware",
    "negotiate_format",
    "FormatMiddleware",
    "strip_format_suffix",
]
