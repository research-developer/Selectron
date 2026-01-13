"""
Selectron WebSpec Server

A Sanic-based REST API server implementing the WebSpec URL grammar for
browser automation and Page Object Model management.

URL Structure:
    {app}.pom.localhost/{root}/{collection}/{id}{.format}

Path Roots:
    /pom/ - Page Object Model definitions and operations
    /dom/ - Direct DOM/WebDriver element interactions
    /orm/ - Object-Relational Mapping for data bindings
    /llm/ - AI/LLM assistance for element discovery
    /wim/ - Window Interface Manager for app control

Example URLs:
    claude.pom.localhost/pom/elements/chat_textarea.json
    obsidian.pom.localhost/dom/elements/ref_123/click
    cursor.pom.localhost/wim/windows/main/maximize
"""

from .app import create_app
from .config import ServerConfig, get_server_config

__all__ = ["create_app", "ServerConfig", "get_server_config"]
