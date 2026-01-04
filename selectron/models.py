"""
Selectron Data Models

Core data models for the Selectron library.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Any, Dict, List, Set
import json


class SessionOrigin(Enum):
    """How the session was discovered or created."""
    OURS = "ours"           # Started by Selectron
    EXTERNAL = "external"   # Discovered running externally


class SessionStatus(Enum):
    """Current status of a debugging session."""
    RUNNING = "running"         # Process is running and responsive
    TERMINATED = "terminated"   # Process has exited
    DETACHED = "detached"       # We stopped monitoring but didn't kill
    UNKNOWN = "unknown"         # Status not yet verified (e.g., loaded from disk)


@dataclass
class Session:
    """
    Represents an active remote debugging session.

    Attributes:
        session_id: Unique identifier (UUID4)
        port: Remote debugging port
        app_name: Application name
        pid: Process ID (None for external sessions we didn't start)
        started_at: When the session was created/discovered
        started_by: Identifier of who started (e.g., "selectron", "external", user ID)
        origin: Whether we started it or discovered it externally
        status: Current status of the session
        app_bundle_path: Path to the .app bundle (macOS)
        chrome_version: Detected Chrome version in the Electron app
        metadata: Additional metadata for extensibility
    """
    session_id: str
    port: int
    app_name: str
    pid: Optional[int] = None
    started_at: datetime = field(default_factory=datetime.now)
    started_by: str = "selectron"
    origin: SessionOrigin = SessionOrigin.OURS
    status: SessionStatus = SessionStatus.RUNNING
    app_bundle_path: Optional[Path] = None
    chrome_version: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON persistence."""
        return {
            "session_id": self.session_id,
            "port": self.port,
            "app_name": self.app_name,
            "pid": self.pid,
            "started_at": self.started_at.isoformat(),
            "started_by": self.started_by,
            "origin": self.origin.value,
            "status": self.status.value,
            "app_bundle_path": str(self.app_bundle_path) if self.app_bundle_path else None,
            "chrome_version": self.chrome_version,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Session":
        """Deserialize from dictionary."""
        return cls(
            session_id=d["session_id"],
            port=d["port"],
            app_name=d["app_name"],
            pid=d.get("pid"),
            started_at=datetime.fromisoformat(d["started_at"]),
            started_by=d.get("started_by", "unknown"),
            origin=SessionOrigin(d.get("origin", "ours")),
            status=SessionStatus(d.get("status", "unknown")),
            app_bundle_path=Path(d["app_bundle_path"]) if d.get("app_bundle_path") else None,
            chrome_version=d.get("chrome_version"),
            metadata=d.get("metadata", {}),
        )

    def __repr__(self) -> str:
        return (
            f"Session(id={self.session_id[:8]}..., "
            f"app={self.app_name}, "
            f"port={self.port}, "
            f"status={self.status.value})"
        )


@dataclass
class ElectronAppPaths:
    """
    Paths for an Electron-based macOS application.

    Attributes:
        app_bundle: Path to the .app bundle
        binary: Path to the main executable
        electron_framework: Path to the Electron Framework binary
    """
    app_bundle: Path
    binary: Path
    electron_framework: Path

    @classmethod
    def from_app_name(
        cls,
        app_name: str,
        search_dirs: Optional[Set[Path]] = None,
        binary_name: Optional[str] = None,
    ) -> "ElectronAppPaths":
        """
        Create paths from an app name, searching configured directories.

        Args:
            app_name: Name of the application (without .app suffix)
            search_dirs: Directories to search (uses config if not provided)
            binary_name: Name of the binary (defaults to app_name)

        Returns:
            ElectronAppPaths instance

        Raises:
            AppNotFoundError: If the app cannot be found
        """
        from .config import get_config
        from .exceptions import AppNotFoundError

        dirs = search_dirs or get_config().search_dirs
        binary_name = binary_name or app_name

        # Convert to list for ordered searching
        dirs_list = list(dirs)

        for directory in dirs_list:
            app_bundle = directory / f"{app_name}.app"
            if app_bundle.exists():
                return cls(
                    app_bundle=app_bundle,
                    binary=app_bundle / "Contents" / "MacOS" / binary_name,
                    electron_framework=(
                        app_bundle / "Contents" / "Frameworks" /
                        "Electron Framework.framework" / "Versions" / "A" / "Electron Framework"
                    ),
                )

        raise AppNotFoundError(app_name, dirs_list)

    def exists(self) -> bool:
        """Check if all paths exist."""
        return (
            self.app_bundle.exists() and
            self.binary.exists() and
            self.electron_framework.exists()
        )

    def __repr__(self) -> str:
        return f"ElectronAppPaths(app_bundle={self.app_bundle})"
