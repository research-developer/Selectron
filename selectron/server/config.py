"""
Selectron Server Configuration

Server-specific configuration extending the base Selectron config.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Set

from ..config import get_config as get_base_config


# Environment variable names
ENV_SERVER_HOST = "SELECTRON_SERVER_HOST"
ENV_SERVER_PORT = "SELECTRON_SERVER_PORT"
ENV_SERVER_DOMAIN = "SELECTRON_SERVER_DOMAIN"
ENV_POMS_DIR = "SELECTRON_POMS_DIR"

# Default values
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
DEFAULT_DOMAIN = "pom.localhost"

# Valid path roots per WebSpec
VALID_ROOTS = frozenset({"pom", "dom", "orm", "llm", "wim"})

# Supported response formats
SUPPORTED_FORMATS = frozenset({"json", "html", "xml", "yaml"})
DEFAULT_FORMAT = "json"


@dataclass
class ServerConfig:
    """
    Configuration for the WebSpec server.

    Attributes:
        host: Host to bind to
        port: Port to bind to
        domain: Base domain for subdomain routing (e.g., pom.localhost)
        poms_dir: Directory containing POM definitions
        valid_roots: Set of valid path roots
        supported_formats: Set of supported response formats
        default_format: Default response format when not specified
        debug: Enable debug mode
    """
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    domain: str = DEFAULT_DOMAIN
    poms_dir: Path = field(default_factory=lambda: Path.cwd() / "poms")
    valid_roots: frozenset = VALID_ROOTS
    supported_formats: frozenset = SUPPORTED_FORMATS
    default_format: str = DEFAULT_FORMAT
    debug: bool = False

    @classmethod
    def from_environment(cls) -> "ServerConfig":
        """
        Load server configuration from environment variables.

        Environment Variables:
            SELECTRON_SERVER_HOST: Host to bind to
            SELECTRON_SERVER_PORT: Port to bind to
            SELECTRON_SERVER_DOMAIN: Base domain for routing
            SELECTRON_POMS_DIR: Directory for POM definitions
        """
        config = cls()

        # Load from environment
        if host := os.environ.get(ENV_SERVER_HOST):
            config.host = host

        if port := os.environ.get(ENV_SERVER_PORT):
            config.port = int(port)

        if domain := os.environ.get(ENV_SERVER_DOMAIN):
            config.domain = domain

        if poms_dir := os.environ.get(ENV_POMS_DIR):
            config.poms_dir = Path(poms_dir).resolve()

        # Inherit debug from base config or env
        if os.environ.get("SELECTRON_DEBUG", "").lower() in ("1", "true", "yes"):
            config.debug = True

        return config

    def get_pom_path(self, app_name: str) -> Path:
        """Get the POM directory for a specific app."""
        return self.poms_dir / app_name

    def get_element_path(self, app_name: str, collection: str = "elements") -> Path:
        """Get the path to an element definition file."""
        return self.get_pom_path(app_name) / f"{collection}.json"

    def is_valid_root(self, root: str) -> bool:
        """Check if a path root is valid."""
        return root in self.valid_roots

    def is_valid_format(self, fmt: str) -> bool:
        """Check if a format is supported."""
        return fmt in self.supported_formats


# Global singleton
_server_config: Optional[ServerConfig] = None


def get_server_config() -> ServerConfig:
    """
    Get the global server configuration singleton.

    Returns:
        ServerConfig instance loaded from environment
    """
    global _server_config
    if _server_config is None:
        _server_config = ServerConfig.from_environment()
    return _server_config


def reset_server_config() -> None:
    """Reset the server configuration singleton."""
    global _server_config
    _server_config = None


def set_server_config(config: ServerConfig) -> None:
    """Set the server configuration singleton."""
    global _server_config
    _server_config = config
