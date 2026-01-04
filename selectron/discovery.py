"""
Selectron Session Discovery

Port scanning and external session detection for Chrome DevTools Protocol.
"""

import json
import socket
import uuid
import urllib.request
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable, Tuple

from .models import Session, SessionOrigin, SessionStatus
from .registry import SessionRegistry, get_registry
from .config import get_config
from .utils import is_port_in_use


def get_devtools_info(port: int, host: str = "localhost", timeout: float = 1.0) -> Optional[Dict[str, Any]]:
    """
    Query Chrome DevTools protocol for version info.

    Args:
        port: Port to query
        host: Host to query (default: localhost)
        timeout: Request timeout in seconds

    Returns:
        Dict with version info, or None if port doesn't respond to DevTools protocol
    """
    try:
        url = f"http://{host}:{port}/json/version"
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except Exception:
        return None


def get_devtools_targets(port: int, host: str = "localhost", timeout: float = 1.0) -> Optional[List[Dict[str, Any]]]:
    """
    Query Chrome DevTools protocol for available targets (windows/tabs).

    Args:
        port: Port to query
        host: Host to query (default: localhost)
        timeout: Request timeout in seconds

    Returns:
        List of target dicts, or None if port doesn't respond
    """
    try:
        url = f"http://{host}:{port}/json/list"
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except Exception:
        return None


def scan_for_sessions(
    port_range: Optional[Tuple[int, int]] = None,
    host: str = "localhost",
) -> List[Dict[str, Any]]:
    """
    Scan a range of ports for active Chrome DevTools sessions.

    Args:
        port_range: (start, end) port range inclusive (uses config default if None)
        host: Host to scan (default: localhost)

    Returns:
        List of dicts with port and devtools info for each discovered session
    """
    config = get_config()
    start_port, end_port = port_range or config.port_scan_range

    discovered = []
    for port in range(start_port, end_port + 1):
        if is_port_in_use(port, host):
            if info := get_devtools_info(port, host):
                discovered.append({
                    "port": port,
                    "info": info,
                    "browser": info.get("Browser", "Unknown"),
                    "protocol_version": info.get("Protocol-Version"),
                    "webkit_version": info.get("WebKit-Version"),
                    "user_agent": info.get("User-Agent"),
                })

    return discovered


class SessionDiscovery:
    """
    Discovers and tracks external debugging sessions.

    Provides methods to scan for sessions and register them with the registry.

    Example:
        discovery = SessionDiscovery(registry)
        new_sessions = discovery.scan_and_register()
        for session in new_sessions:
            print(f"Found: {session.app_name} on port {session.port}")
    """

    def __init__(self, registry: Optional[SessionRegistry] = None):
        """
        Initialize session discovery.

        Args:
            registry: Session registry (uses global if not provided)
        """
        self._registry = registry or get_registry()
        self._scanned_at: Optional[datetime] = None

    @property
    def last_scan_time(self) -> Optional[datetime]:
        """Time of the last scan."""
        return self._scanned_at

    def scan_and_register(
        self,
        port_range: Optional[Tuple[int, int]] = None,
    ) -> List[Session]:
        """
        Scan for external sessions and register them.

        Only registers sessions that are not already in the registry.

        Args:
            port_range: (start, end) port range to scan

        Returns:
            List of newly discovered and registered sessions
        """
        discovered_sessions = []

        for found in scan_for_sessions(port_range):
            port = found["port"]

            # Check if we already know about this port
            if self._registry.get_by_port(port):
                continue

            # Extract app name from browser string if possible
            browser = found["browser"]
            app_name = self._guess_app_name(browser, port)

            session = Session(
                session_id=str(uuid.uuid4()),
                port=port,
                app_name=app_name,
                pid=None,  # Unknown for external sessions
                started_at=datetime.now(),
                started_by="external",
                origin=SessionOrigin.EXTERNAL,
                status=SessionStatus.RUNNING,
                metadata={
                    "browser": browser,
                    "protocol_version": found.get("protocol_version"),
                    "webkit_version": found.get("webkit_version"),
                    "user_agent": found.get("user_agent"),
                    "discovered_at": datetime.now().isoformat(),
                },
            )

            try:
                self._registry.register(session)
                discovered_sessions.append(session)
            except Exception as e:
                print(f"Warning: Could not register session on port {port}: {e}")

        self._scanned_at = datetime.now()
        return discovered_sessions

    def rescan(self, port_range: Optional[Tuple[int, int]] = None) -> List[Session]:
        """
        Rescan for external sessions.

        Alias for scan_and_register() for explicit rescan requests.
        """
        return self.scan_and_register(port_range)

    def scan_single_port(self, port: int) -> Optional[Session]:
        """
        Scan a single port and register if found.

        Args:
            port: Port to scan

        Returns:
            Session if discovered and registered, None otherwise
        """
        sessions = self.scan_and_register(port_range=(port, port))
        return sessions[0] if sessions else None

    def _guess_app_name(self, browser_string: str, port: int) -> str:
        """
        Attempt to guess the app name from browser info.

        Falls back to "Unknown (port XXXX)" if can't determine.

        Args:
            browser_string: Browser identification string
            port: Port number

        Returns:
            Guessed app name
        """
        browser_lower = browser_string.lower()

        # Common patterns
        if "electron" in browser_lower:
            return f"Electron App (port {port})"
        elif "chrome" in browser_lower:
            # Extract version if available
            if "/" in browser_string:
                version = browser_string.split("/")[1].split(".")[0]
                return f"Chrome {version} (port {port})"
            return f"Chrome (port {port})"
        elif "chromium" in browser_lower:
            return f"Chromium (port {port})"
        else:
            return f"Unknown (port {port})"


# Action types for port conflict resolution
CONFLICT_ACTION_ADD = "add"       # Add existing session to registry
CONFLICT_ACTION_IGNORE = "ignore"  # Ignore and continue
CONFLICT_ACTION_KILL = "kill"      # Kill existing and take over
CONFLICT_ACTION_CANCEL = "cancel"  # Cancel the operation


class PortConflictHandler:
    """
    Handles port conflicts when starting new sessions.

    Provides options:
        - add: Track existing session in registry
        - ignore: Proceed without tracking
        - kill: Kill existing process and take over
        - cancel: Abort the operation

    Example:
        handler = PortConflictHandler(registry, discovery)

        def prompt(port, session):
            # Show UI to user
            return "add"  # or "ignore", "kill", "cancel"

        action, session = handler.check_and_prompt(9222, prompt)
    """

    def __init__(
        self,
        registry: Optional[SessionRegistry] = None,
        discovery: Optional[SessionDiscovery] = None,
    ):
        """
        Initialize conflict handler.

        Args:
            registry: Session registry (uses global if not provided)
            discovery: Session discovery (creates new if not provided)
        """
        self._registry = registry or get_registry()
        self._discovery = discovery or SessionDiscovery(self._registry)

    def check_port(self, port: int) -> Tuple[bool, Optional[Session]]:
        """
        Check if a port is available.

        Args:
            port: Port to check

        Returns:
            Tuple of (is_available, existing_session)
        """
        # First check registry
        existing = self._registry.get_by_port(port)
        if existing:
            return (False, existing)

        # Then check if port is actually in use
        if is_port_in_use(port):
            # Try to discover what's using it
            if session := self._discovery.scan_single_port(port):
                return (False, session)
            # Port in use but can't identify
            return (False, None)

        return (True, None)

    def check_and_prompt(
        self,
        port: int,
        prompt_callback: Optional[Callable[[int, Optional[Session]], str]] = None,
    ) -> Tuple[str, Optional[Session]]:
        """
        Check for port conflict and handle it.

        Args:
            port: Port to check
            prompt_callback: Function to call for user input.
                           Receives (port, existing_session) and should return
                           one of: 'add', 'ignore', 'kill', 'cancel'

        Returns:
            Tuple of (action_taken, existing_session)
            action_taken is one of:
                - 'available': Port is free
                - 'add': Session added to registry
                - 'ignore': Conflict ignored
                - 'kill': Request to kill existing
                - 'cancel': Operation cancelled
                - 'conflict': Conflict detected (no callback provided)
        """
        is_available, existing = self.check_port(port)

        if is_available:
            return ("available", None)

        if prompt_callback:
            action = prompt_callback(port, existing)

            if action == CONFLICT_ACTION_ADD:
                # Already in registry from discovery, just return
                return ("add", existing)
            elif action == CONFLICT_ACTION_IGNORE:
                return ("ignore", existing)
            elif action == CONFLICT_ACTION_KILL:
                return ("kill", existing)
            elif action == CONFLICT_ACTION_CANCEL:
                return ("cancel", existing)
            else:
                print(f"Unknown conflict action: {action}")
                return ("cancel", existing)
        else:
            # No callback - just report the conflict
            return ("conflict", existing)


def default_conflict_prompt(port: int, existing: Optional[Session]) -> str:
    """
    Default interactive prompt for port conflicts.

    Args:
        port: Conflicting port
        existing: Existing session on that port

    Returns:
        User's chosen action
    """
    if existing:
        print(f"\nPort {port} is in use by: {existing.app_name}")
        print(f"  Session ID: {existing.session_id[:8]}...")
        print(f"  Origin: {existing.origin.value}")
        print(f"  Status: {existing.status.value}")
    else:
        print(f"\nPort {port} is in use by an unknown process")

    print("\nOptions:")
    print("  [a]dd    - Add to registry and track")
    print("  [i]gnore - Proceed without tracking")
    print("  [k]ill   - Kill existing and take over")
    print("  [c]ancel - Abort operation")

    while True:
        choice = input("\nChoice [a/i/k/c]: ").strip().lower()
        if choice in ("a", "add"):
            return CONFLICT_ACTION_ADD
        elif choice in ("i", "ignore"):
            return CONFLICT_ACTION_IGNORE
        elif choice in ("k", "kill"):
            return CONFLICT_ACTION_KILL
        elif choice in ("c", "cancel", ""):
            return CONFLICT_ACTION_CANCEL
        else:
            print("Invalid choice. Please enter a, i, k, or c.")
