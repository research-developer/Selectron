"""
Selectron Process Monitor

Background daemon thread that monitors process lifecycle and auto-cleans terminated sessions.
"""

import atexit
import signal
import subprocess
import threading
import time
from typing import Optional, Callable, Dict

from .registry import SessionRegistry, get_registry
from .models import Session, SessionStatus, SessionOrigin


class ProcessMonitor:
    """
    Background daemon thread that monitors process status.

    Uses proc.poll() to detect when processes terminate and
    automatically updates the session registry.

    Features:
        - Daemon thread with configurable poll interval
        - Auto-removes sessions from registry on termination
        - Optional callback on process termination
        - Detach capability (stop monitoring without killing)
        - Signal handlers for graceful cleanup

    Example:
        monitor = ProcessMonitor(registry)
        monitor.start()

        # Track a process
        monitor.track_process(session, proc)

        # Later, detach without killing
        monitor.detach_session(session.session_id)

        # Or kill and remove
        monitor.kill_session(session.session_id)
    """

    def __init__(
        self,
        registry: Optional[SessionRegistry] = None,
        poll_interval: float = 1.0,
        on_termination: Optional[Callable[[Session, int], None]] = None,
    ):
        """
        Initialize the process monitor.

        Args:
            registry: Session registry (uses global if not provided)
            poll_interval: How often to check processes (seconds)
            on_termination: Callback when a process terminates.
                           Called with (session, return_code)
        """
        self._registry = registry or get_registry()
        self._poll_interval = poll_interval
        self._on_termination = on_termination

        # Map session_id -> Popen object for "our" processes
        self._processes: Dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()

        # Monitor thread
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Track if we've registered signal handlers
        self._handlers_registered = False

    def start(self) -> None:
        """Start the monitor daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop,
            name="SelectronProcessMonitor",
            daemon=True,  # Will be killed when main thread exits
        )
        self._thread.start()

        # Register cleanup handlers (only once)
        if not self._handlers_registered:
            atexit.register(self._cleanup)
            # Only register signal handlers if we're in the main thread
            try:
                if threading.current_thread() is threading.main_thread():
                    signal.signal(signal.SIGTERM, self._signal_handler)
                    signal.signal(signal.SIGINT, self._signal_handler)
            except ValueError:
                # Signal handlers can only be set in main thread
                pass
            self._handlers_registered = True

    def stop(self, timeout: float = 5.0) -> None:
        """
        Stop the monitor daemon thread.

        Args:
            timeout: Maximum time to wait for thread to stop
        """
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def is_running(self) -> bool:
        """Check if the monitor thread is running."""
        return self._thread is not None and self._thread.is_alive()

    def track_process(self, session: Session, process: subprocess.Popen) -> None:
        """
        Start tracking a process for a session.

        Args:
            session: Session object for this process
            process: Popen object for the process
        """
        with self._lock:
            self._processes[session.session_id] = process

    def untrack_process(self, session_id: str) -> Optional[subprocess.Popen]:
        """
        Stop tracking a process (does not kill it).

        Args:
            session_id: Session ID to stop tracking

        Returns:
            The Popen object if found, None otherwise
        """
        with self._lock:
            return self._processes.pop(session_id, None)

    def get_process(self, session_id: str) -> Optional[subprocess.Popen]:
        """
        Get the Popen object for a session.

        Args:
            session_id: Session ID to look up

        Returns:
            The Popen object if found, None otherwise
        """
        with self._lock:
            return self._processes.get(session_id)

    def detach_session(self, session_id: str) -> bool:
        """
        Detach a session - stop monitoring without killing the process.

        Args:
            session_id: Session ID to detach

        Returns:
            True if successfully detached, False if not found
        """
        proc = self.untrack_process(session_id)
        if proc:
            self._registry.update_status(session_id, SessionStatus.DETACHED)
            return True
        return False

    def kill_session(self, session_id: str, timeout: float = 5.0) -> bool:
        """
        Kill a session's process.

        First attempts graceful termination (SIGTERM), then force kills
        (SIGKILL) if the process doesn't exit within timeout.

        Args:
            session_id: Session ID to kill
            timeout: Maximum time to wait for graceful termination

        Returns:
            True if killed, False if not found or already dead
        """
        with self._lock:
            proc = self._processes.get(session_id)

        if not proc:
            return False

        try:
            # Try graceful termination first
            proc.terminate()
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # Force kill if graceful termination fails
                proc.kill()
                proc.wait(timeout=1.0)

            # Remove from tracking
            self.untrack_process(session_id)
            self._registry.update_status(session_id, SessionStatus.TERMINATED)
            return True

        except OSError as e:
            print(f"Error killing process: {e}")
            return False

    def kill_all(self, timeout: float = 5.0) -> int:
        """
        Kill all tracked processes.

        Args:
            timeout: Maximum time to wait for each process

        Returns:
            Number of processes killed
        """
        with self._lock:
            session_ids = list(self._processes.keys())

        killed = 0
        for session_id in session_ids:
            if self.kill_session(session_id, timeout):
                killed += 1

        return killed

    def _monitor_loop(self) -> None:
        """Main monitoring loop - runs in daemon thread."""
        while not self._stop_event.is_set():
            self._check_processes()
            self._stop_event.wait(timeout=self._poll_interval)

    def _check_processes(self) -> None:
        """Check all tracked processes and update registry."""
        with self._lock:
            session_ids = list(self._processes.keys())

        for session_id in session_ids:
            with self._lock:
                proc = self._processes.get(session_id)

            if proc is None:
                continue

            returncode = proc.poll()
            if returncode is not None:
                # Process has terminated
                with self._lock:
                    self._processes.pop(session_id, None)

                session = self._registry.get_by_id(session_id)
                if session:
                    self._registry.update_status(session_id, SessionStatus.TERMINATED)

                    # Call termination callback
                    if self._on_termination:
                        try:
                            self._on_termination(session, returncode)
                        except Exception as e:
                            print(f"Error in termination callback: {e}")

    def _cleanup(self) -> None:
        """Clean up on exit."""
        self.stop()

    def _signal_handler(self, signum, frame) -> None:
        """Handle termination signals."""
        self._cleanup()
        # Re-raise to allow default handler
        signal.signal(signum, signal.SIG_DFL)
        signal.raise_signal(signum)


# Module-level singleton
_monitor: Optional[ProcessMonitor] = None
_monitor_lock = threading.Lock()


def get_monitor(registry: Optional[SessionRegistry] = None) -> ProcessMonitor:
    """
    Get or create the global process monitor.

    Args:
        registry: Session registry to use (only used on first call)

    Returns:
        ProcessMonitor singleton instance
    """
    global _monitor
    with _monitor_lock:
        if _monitor is None:
            _monitor = ProcessMonitor(registry)
            _monitor.start()
        return _monitor


def reset_monitor() -> None:
    """Reset the global monitor singleton (useful for testing)."""
    global _monitor
    with _monitor_lock:
        if _monitor:
            _monitor.stop()
        _monitor = None
