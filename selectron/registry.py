"""
Selectron Session Registry

Thread-safe registry for tracking active debugging sessions with file persistence.
"""

import fcntl
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Iterator, List, Dict

from .models import Session, SessionStatus, SessionOrigin
from .config import get_config
from .exceptions import PortConflictError, SessionNotFoundError


class SessionRegistry:
    """
    Thread-safe registry for tracking active debugging sessions.

    Provides both in-memory access and file-based persistence for
    recovery after restarts.

    Features:
        - Thread-safe with RLock (reentrant lock)
        - O(1) port lookups via port index
        - Atomic file writes with file locking
        - Auto-load from disk on startup

    Example:
        registry = SessionRegistry()
        registry.register(session)
        session = registry.get_by_port(9222)
        registry.unregister(session.session_id)
    """

    def __init__(self, persistence_path: Optional[Path] = None):
        """
        Initialize the session registry.

        Args:
            persistence_path: Path to save sessions (defaults to ~/.selectron/sessions.json)
        """
        self._sessions: Dict[str, Session] = {}  # session_id -> Session
        self._port_index: Dict[int, str] = {}    # port -> session_id (for fast lookup)
        self._lock = threading.RLock()           # Reentrant lock for thread safety
        self._persistence_path = persistence_path or get_config().sessions_file

        # Ensure directory exists
        self._persistence_path.parent.mkdir(parents=True, exist_ok=True)

        # Load persisted sessions on startup
        self._load_from_disk()

    def register(self, session: Session) -> None:
        """
        Add a session to the registry.

        Args:
            session: Session to register

        Raises:
            PortConflictError: If the port is already in use by another session
        """
        with self._lock:
            if session.port in self._port_index:
                existing_id = self._port_index[session.port]
                existing = self._sessions.get(existing_id)
                raise PortConflictError(session.port, existing)

            self._sessions[session.session_id] = session
            self._port_index[session.port] = session.session_id
            self._persist_to_disk()

    def unregister(self, session_id: str) -> Optional[Session]:
        """
        Remove a session from the registry.

        Args:
            session_id: ID of the session to remove

        Returns:
            The removed session, or None if not found
        """
        with self._lock:
            if session := self._sessions.pop(session_id, None):
                self._port_index.pop(session.port, None)
                self._persist_to_disk()
                return session
            return None

    def get_by_id(self, session_id: str) -> Optional[Session]:
        """Get a session by its ID."""
        with self._lock:
            return self._sessions.get(session_id)

    def get_by_port(self, port: int) -> Optional[Session]:
        """Get a session by its debugging port."""
        with self._lock:
            if session_id := self._port_index.get(port):
                return self._sessions.get(session_id)
            return None

    def get_by_app(self, app_name: str) -> List[Session]:
        """Get all sessions for a given app name."""
        with self._lock:
            return [s for s in self._sessions.values() if s.app_name == app_name]

    def get_our_sessions(self) -> List[Session]:
        """Get sessions started by Selectron (not external)."""
        with self._lock:
            return [
                s for s in self._sessions.values()
                if s.origin == SessionOrigin.OURS
            ]

    def get_external_sessions(self) -> List[Session]:
        """Get externally-discovered sessions."""
        with self._lock:
            return [
                s for s in self._sessions.values()
                if s.origin == SessionOrigin.EXTERNAL
            ]

    def get_running_sessions(self) -> List[Session]:
        """Get all sessions with RUNNING status."""
        with self._lock:
            return [
                s for s in self._sessions.values()
                if s.status == SessionStatus.RUNNING
            ]

    def update_status(self, session_id: str, status: SessionStatus) -> bool:
        """
        Update the status of a session.

        Args:
            session_id: ID of the session to update
            status: New status

        Returns:
            True if session was found and updated, False otherwise
        """
        with self._lock:
            if session := self._sessions.get(session_id):
                session.status = status
                if status == SessionStatus.TERMINATED:
                    # Remove terminated sessions
                    self.unregister(session_id)
                else:
                    self._persist_to_disk()
                return True
            return False

    def all_sessions(self) -> List[Session]:
        """Get a list of all sessions (thread-safe snapshot)."""
        with self._lock:
            return list(self._sessions.values())

    def __iter__(self) -> Iterator[Session]:
        """Iterate over all sessions (thread-safe snapshot)."""
        with self._lock:
            return iter(list(self._sessions.values()))

    def __len__(self) -> int:
        """Return the number of sessions."""
        with self._lock:
            return len(self._sessions)

    def __contains__(self, session_id: str) -> bool:
        """Check if a session ID is in the registry."""
        with self._lock:
            return session_id in self._sessions

    def clear(self) -> None:
        """Remove all sessions from the registry."""
        with self._lock:
            self._sessions.clear()
            self._port_index.clear()
            self._persist_to_disk()

    def _persist_to_disk(self) -> None:
        """Save current state to disk with file locking."""
        data = {
            "version": 1,
            "updated_at": datetime.now().isoformat(),
            "sessions": [s.to_dict() for s in self._sessions.values()],
        }

        # Atomic write with file locking
        temp_path = self._persistence_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    json.dump(data, f, indent=2)
                    f.flush()
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            temp_path.replace(self._persistence_path)
        except IOError as e:
            print(f"Warning: Could not persist sessions: {e}")
            if temp_path.exists():
                temp_path.unlink()

    def _load_from_disk(self) -> None:
        """Load persisted sessions from disk."""
        if not self._persistence_path.exists():
            return

        try:
            with open(self._persistence_path, "r") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    data = json.load(f)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            for session_dict in data.get("sessions", []):
                try:
                    session = Session.from_dict(session_dict)
                    # Mark as unknown status until verified
                    session.status = SessionStatus.UNKNOWN
                    self._sessions[session.session_id] = session
                    self._port_index[session.port] = session.session_id
                except Exception as e:
                    # Log and skip corrupted entries
                    print(f"Warning: Could not load session: {e}")

        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load sessions file: {e}")

    def verify_sessions(self) -> Dict[str, SessionStatus]:
        """
        Verify the status of all sessions by checking if their ports are in use.

        Returns:
            Dict mapping session_id to verified status
        """
        from .utils import is_port_in_use

        results = {}
        with self._lock:
            for session_id, session in list(self._sessions.items()):
                if session.status == SessionStatus.UNKNOWN:
                    if is_port_in_use(session.port):
                        session.status = SessionStatus.RUNNING
                    else:
                        session.status = SessionStatus.TERMINATED
                        self.unregister(session_id)
                    results[session_id] = session.status

        return results


# Module-level singleton
_registry: Optional[SessionRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> SessionRegistry:
    """
    Get or create the global session registry.

    Returns:
        SessionRegistry singleton instance
    """
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = SessionRegistry()
        return _registry


def reset_registry() -> None:
    """Reset the global registry singleton (useful for testing)."""
    global _registry
    with _registry_lock:
        _registry = None
