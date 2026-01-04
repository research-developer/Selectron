"""
Selectron Electron Driver Manager

Main interface for managing Electron app automation via Selenium.
"""

import json
import re
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

from .config import get_config, SelectronConfig
from .models import ElectronAppPaths, Session, SessionOrigin, SessionStatus
from .registry import SessionRegistry, get_registry
from .monitor import ProcessMonitor, get_monitor
from .discovery import (
    SessionDiscovery,
    PortConflictHandler,
    is_port_in_use,
    default_conflict_prompt,
    CONFLICT_ACTION_KILL,
    CONFLICT_ACTION_CANCEL,
    CONFLICT_ACTION_IGNORE,
)
from .utils import get_selenium_manager_path, find_available_port
from .exceptions import (
    ChromeVersionError,
    DriverInstallError,
    SessionStartError,
    PortConflictError,
)


class ElectronDriverManager:
    """
    Manages ChromeDriver installation and session lifecycle for Electron apps.

    This is the main interface for automating Electron applications. It handles:
        - Auto-detection of Chrome version from Electron apps
        - ChromeDriver installation via selenium-manager
        - Session lifecycle management with registry integration
        - Process monitoring with auto-cleanup
        - Port conflict resolution

    Example:
        # Basic usage
        edm = ElectronDriverManager(app_name="Claude")
        session = edm.start_app_with_debugging(port=9222)
        driver = edm.create_local_driver()

        # Interact with the app
        print(driver.title)

        # Clean up
        driver.quit()
        edm.stop_session()

    Environment Variables:
        SELECTRON_DEFAULT_APP: Default app name if not specified
        SELECTRON_DEFAULT_APP_DIR: First directory to search for apps
    """

    def __init__(
        self,
        app_name: Optional[str] = None,
        app_dir: Optional[Path] = None,
        electron_binary_path: Optional[Path] = None,
        electron_framework_path: Optional[Path] = None,
        registry: Optional[SessionRegistry] = None,
        monitor: Optional[ProcessMonitor] = None,
        auto_start_monitor: bool = True,
    ):
        """
        Initialize the Electron Driver Manager.

        Args:
            app_name: Name of the Electron app (e.g., "Claude", "Obsidian")
                     If not provided, uses SELECTRON_DEFAULT_APP env var
            app_dir: Additional directory to search for the app
            electron_binary_path: Explicit path to the Electron binary
            electron_framework_path: Explicit path to the Electron Framework
            registry: Session registry (uses global if not provided)
            monitor: Process monitor (uses global if not provided)
            auto_start_monitor: Start the monitor daemon automatically

        Raises:
            ValueError: If no app_name is provided and SELECTRON_DEFAULT_APP is not set
            AppNotFoundError: If the app cannot be found in any search directory
        """
        config = get_config()

        # Use default app from config if not specified
        self.app_name = app_name or config.default_app
        if not self.app_name:
            raise ValueError(
                "app_name required. Either pass it explicitly or set "
                "SELECTRON_DEFAULT_APP environment variable."
            )

        # Resolve paths
        if electron_binary_path and electron_framework_path:
            self.paths = ElectronAppPaths(
                app_bundle=electron_binary_path.parent.parent.parent,
                binary=electron_binary_path,
                electron_framework=electron_framework_path,
            )
        else:
            # Build search dirs with app_dir prepended if provided
            search_dirs = config.search_dirs.copy()
            if app_dir:
                search_dirs.add(Path(app_dir).resolve())
            self.paths = ElectronAppPaths.from_app_name(self.app_name, search_dirs)

        # Registry and monitor
        self._registry = registry or get_registry()
        self._monitor = monitor or get_monitor(self._registry)

        if auto_start_monitor and not self._monitor.is_running():
            self._monitor.start()

        # Discovery and conflict handling
        self._discovery = SessionDiscovery(self._registry)
        self._conflict_handler = PortConflictHandler(self._registry, self._discovery)

        # Cached values
        self._chrome_version: Optional[str] = None
        self._driver_path: Optional[Path] = None

        # Current session
        self._current_session: Optional[Session] = None

        print(f"Electron binary: {self.paths.binary}")
        print(f"Electron framework: {self.paths.electron_framework}")

    @property
    def current_session(self) -> Optional[Session]:
        """The currently active session, if any."""
        return self._current_session

    @property
    def registry(self) -> SessionRegistry:
        """The session registry."""
        return self._registry

    @property
    def monitor(self) -> ProcessMonitor:
        """The process monitor."""
        return self._monitor

    def get_chrome_version(self) -> str:
        """
        Extract the Chrome version embedded in the Electron app.

        Uses the `strings` command to search the Electron Framework binary
        for the Chrome version string (e.g., "Chrome/138.0.7204.251").

        Returns:
            Full Chrome version string (e.g., "138.0.7204.251")

        Raises:
            ChromeVersionError: If the version cannot be determined
        """
        if self._chrome_version:
            return self._chrome_version

        if not self.paths.electron_framework.exists():
            raise ChromeVersionError(
                self.paths.electron_framework,
                "Framework file not found"
            )

        try:
            process = subprocess.run(
                ["strings", str(self.paths.electron_framework)],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            raise ChromeVersionError(
                self.paths.electron_framework,
                "Timeout reading framework binary"
            )

        # Look for pattern like "Chrome/138.0.7204.251 Electron/37.10.3"
        match = re.search(r'Chrome/(\d+\.\d+\.\d+\.\d+)\s+Electron/', process.stdout)

        if match:
            self._chrome_version = match.group(1)
            return self._chrome_version

        raise ChromeVersionError(
            self.paths.electron_framework,
            "Could not find Chrome version pattern in binary"
        )

    def get_major_version(self) -> str:
        """Get just the major version number (e.g., '138' from '138.0.7204.251')."""
        return self.get_chrome_version().split('.')[0]

    def install(self, force: bool = False) -> Path:
        """
        Install the matching ChromeDriver version using selenium-manager.

        Args:
            force: If True, re-download even if cached

        Returns:
            Path to the chromedriver executable

        Raises:
            DriverInstallError: If installation fails
        """
        if self._driver_path and not force:
            return self._driver_path

        major_version = self.get_major_version()
        print(f"Detected Chrome version: {self.get_chrome_version()}")
        print(f"Requesting ChromeDriver for Chrome {major_version}...")

        try:
            sm_path = get_selenium_manager_path()
        except (RuntimeError, FileNotFoundError) as e:
            raise DriverInstallError(major_version, str(e))

        cmd = [
            str(sm_path),
            "--browser", "chrome",
            "--browser-version", major_version,
            "--output", "JSON",
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            raise DriverInstallError(major_version, "Timeout waiting for selenium-manager")

        if result.returncode != 0:
            raise DriverInstallError(
                major_version,
                result.stderr or result.stdout or "Unknown error"
            )

        try:
            data = json.loads(result.stdout)
            if driver_path := data.get("result", {}).get("driver_path"):
                self._driver_path = Path(driver_path)
                print(f"ChromeDriver installed at: {self._driver_path}")
                return self._driver_path
        except json.JSONDecodeError:
            pass

        raise DriverInstallError(
            major_version,
            f"Could not parse selenium-manager output: {result.stdout}"
        )

    def start_app_with_debugging(
        self,
        debugging_port: int = 9222,
        wait_seconds: float = 5.0,
        on_conflict: Optional[Callable[[int, Optional[Session]], str]] = None,
        auto_find_port: bool = False,
    ) -> Optional[Session]:
        """
        Start the Electron app with remote debugging enabled.

        Args:
            debugging_port: Port for remote debugging (default: 9222)
            wait_seconds: Max time to wait for port to become available
            on_conflict: Callback for port conflicts.
                        Receives (port, existing_session) and should return
                        one of: 'add', 'ignore', 'kill', 'cancel'
                        If None and conflict occurs, uses interactive prompt.
            auto_find_port: If True, automatically find an available port

        Returns:
            Session object for the started app, or None if startup failed/cancelled

        Raises:
            SessionStartError: If the app fails to start
        """
        # Auto-find port if requested
        if auto_find_port:
            debugging_port = find_available_port(debugging_port)
            print(f"Using port {debugging_port}")

        # Check for port conflict
        action, existing = self._conflict_handler.check_and_prompt(
            debugging_port,
            on_conflict or default_conflict_prompt
        )

        if action == "available":
            pass  # Port is free, continue
        elif action == CONFLICT_ACTION_CANCEL or action == "conflict":
            print(f"Operation cancelled")
            return None
        elif action == CONFLICT_ACTION_KILL and existing:
            # Kill existing session
            if existing.origin == SessionOrigin.OURS:
                print(f"Killing existing session...")
                self._monitor.kill_session(existing.session_id)
                time.sleep(0.5)  # Brief pause for port to free up
            else:
                print(f"Cannot kill external session. Use system tools to terminate.")
                return None
        elif action == CONFLICT_ACTION_IGNORE:
            print(f"Ignoring existing session on port {debugging_port}")
            return existing
        elif action == "add":
            # Just tracking existing
            return existing

        # Start the process
        args = [str(self.paths.binary), f"--remote-debugging-port={debugging_port}"]
        print(f"Starting: {' '.join(args)}")

        try:
            proc = subprocess.Popen(args)
        except OSError as e:
            raise SessionStartError(self.app_name, debugging_port, str(e))

        # Create session record
        session = Session(
            session_id=str(uuid.uuid4()),
            port=debugging_port,
            app_name=self.app_name,
            pid=proc.pid,
            started_at=datetime.now(),
            started_by="selectron",
            origin=SessionOrigin.OURS,
            status=SessionStatus.RUNNING,
            app_bundle_path=self.paths.app_bundle,
            chrome_version=self._chrome_version,
        )

        # Register and track
        try:
            self._registry.register(session)
            self._monitor.track_process(session, proc)
        except PortConflictError:
            proc.terminate()
            raise

        # Wait for port to become available
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            if is_port_in_use(debugging_port):
                print(f"App started, DevTools listening on port {debugging_port}")
                self._current_session = session
                return session
            time.sleep(0.1)

        print(f"Warning: Port {debugging_port} not open after {wait_seconds}s")
        self._current_session = session
        return session

    def stop_session(self, session_id: Optional[str] = None, timeout: float = 5.0) -> bool:
        """
        Stop a debugging session.

        Args:
            session_id: Session to stop (uses current session if not provided)
            timeout: Maximum time to wait for graceful termination

        Returns:
            True if session was stopped, False otherwise
        """
        sid = session_id or (self._current_session.session_id if self._current_session else None)
        if not sid:
            print("No session to stop")
            return False

        result = self._monitor.kill_session(sid, timeout)
        if result and self._current_session and self._current_session.session_id == sid:
            self._current_session = None
        return result

    def detach_session(self, session_id: Optional[str] = None) -> bool:
        """
        Detach from a session without killing it.

        The app continues running but we stop monitoring it.

        Args:
            session_id: Session to detach (uses current session if not provided)

        Returns:
            True if session was detached, False otherwise
        """
        sid = session_id or (self._current_session.session_id if self._current_session else None)
        if not sid:
            print("No session to detach")
            return False

        result = self._monitor.detach_session(sid)
        if result and self._current_session and self._current_session.session_id == sid:
            self._current_session = None
        return result

    def create_local_driver(
        self,
        debugging_port: Optional[int] = None,
    ) -> webdriver.Chrome:
        """
        Create a local Chrome WebDriver connected to the running Electron app.

        This uses the locally-installed ChromeDriver (via install()) to connect
        to an already-running Electron app with debugging enabled.

        Args:
            debugging_port: Port to connect to (uses current session's port if not provided)

        Returns:
            Chrome WebDriver instance

        Raises:
            ValueError: If no port is specified and no current session exists
        """
        port = debugging_port
        if port is None:
            if self._current_session:
                port = self._current_session.port
            else:
                port = 9222  # Default fallback

        driver_path = self.install()

        options = Options()
        options.binary_location = str(self.paths.binary)
        options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")

        service = Service(executable_path=str(driver_path))

        return webdriver.Chrome(options=options, service=service)

    def create_remote_driver(
        self,
        server_url: str = "http://localhost:4041",
        debugging_port: Optional[int] = None,
    ) -> webdriver.Remote:
        """
        Create a Remote WebDriver connected via Selenium Grid.

        IMPORTANT: The Selenium Grid server must have access to a ChromeDriver
        version that matches this Electron app's Chrome version.

        Args:
            server_url: URL of the Selenium Grid server
            debugging_port: Port to connect to (uses current session's port if not provided)

        Returns:
            Remote WebDriver instance

        Raises:
            ValueError: If no port is specified and no current session exists
        """
        port = debugging_port
        if port is None:
            if self._current_session:
                port = self._current_session.port
            else:
                port = 9222  # Default fallback

        options = Options()
        options.binary_location = str(self.paths.binary)
        options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")

        return webdriver.Remote(
            command_executor=server_url,
            options=options,
        )

    def get_options(self, debugging_port: Optional[int] = None) -> Options:
        """
        Get Chrome options configured for this Electron app.

        Args:
            debugging_port: Port to connect to (uses current session's port if not provided)

        Returns:
            Chrome Options instance
        """
        port = debugging_port
        if port is None:
            if self._current_session:
                port = self._current_session.port
            else:
                port = 9222

        options = Options()
        options.binary_location = str(self.paths.binary)
        options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
        return options

    def scan_for_external_sessions(self) -> list:
        """
        Scan for externally-started debugging sessions.

        Returns:
            List of newly discovered Session objects
        """
        return self._discovery.scan_and_register()


# ============================================================================
# Utility functions
# ============================================================================

def send_shortcut(driver: webdriver.Remote, key: str, *modifiers: Keys) -> None:
    """
    Send a keyboard shortcut to the active element.

    Args:
        driver: WebDriver instance
        key: Key to press
        modifiers: Modifier keys (e.g., Keys.COMMAND, Keys.SHIFT)

    Example:
        send_shortcut(driver, 'j', Keys.COMMAND)  # Cmd+J
        send_shortcut(driver, 'k', Keys.COMMAND, Keys.SHIFT)  # Cmd+Shift+K
    """
    action = ActionChains(driver)
    for modifier in modifiers:
        action.key_down(modifier)
    action.send_keys(key)
    for modifier in reversed(modifiers):
        action.key_up(modifier)
    action.perform()
