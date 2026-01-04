"""
Selectron Exceptions

Custom exceptions for the Selectron library.
"""

from typing import Optional, List
from pathlib import Path


class SelectronError(Exception):
    """Base exception for all Selectron errors."""
    pass


class PortConflictError(SelectronError):
    """Raised when attempting to use a port that's already in use."""

    def __init__(self, port: int, existing_session: Optional["Session"] = None):
        self.port = port
        self.existing_session = existing_session
        msg = f"Port {port} is already in use"
        if existing_session:
            msg += f" by session {existing_session.session_id}"
        super().__init__(msg)


class AppNotFoundError(SelectronError):
    """Raised when an Electron app cannot be found in any search directory."""

    def __init__(self, app_name: str, searched_dirs: List[Path]):
        self.app_name = app_name
        self.searched_dirs = searched_dirs
        super().__init__(
            f"Could not find {app_name}.app in {[str(d) for d in searched_dirs]}"
        )


class ChromeVersionError(SelectronError):
    """Raised when the Chrome version cannot be determined from the Electron framework."""

    def __init__(self, framework_path: Path, reason: Optional[str] = None):
        self.framework_path = framework_path
        self.reason = reason
        msg = f"Could not determine Chrome version from {framework_path}"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)


class SessionNotFoundError(SelectronError):
    """Raised when a session cannot be found in the registry."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"Session not found: {session_id}")


class DriverInstallError(SelectronError):
    """Raised when ChromeDriver installation fails."""

    def __init__(self, version: str, reason: Optional[str] = None):
        self.version = version
        self.reason = reason
        msg = f"Failed to install ChromeDriver for Chrome {version}"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)


class SessionStartError(SelectronError):
    """Raised when a debugging session fails to start."""

    def __init__(self, app_name: str, port: int, reason: Optional[str] = None):
        self.app_name = app_name
        self.port = port
        self.reason = reason
        msg = f"Failed to start debugging session for {app_name} on port {port}"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)
