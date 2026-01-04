"""
Selectron Service Architecture (Future)

This module provides the foundation for a detached service mode that can:
1. Monitor sessions independently of the parent process
2. Detect when the parent process dies
3. Prompt user for actions (kill, attach, record for reattach, launch CLI)
4. Log execution events for ML analysis

NOTE: This is currently a stub. Full implementation is planned for v0.4.0.

ROADMAP:
- v0.4.0: Basic daemon that monitors sessions and detects parent death
- v0.4.1: IPC with parent process (Unix socket or named pipe)
- v0.4.2: macOS Notification Center integration
- v0.5.0: Execution logging for ML analysis
"""

import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any


class ServiceMode(Enum):
    """Operating mode for the Selectron service."""
    EMBEDDED = "embedded"      # Run as part of main process (current behavior)
    DETACHED = "detached"      # Run as separate daemon
    FOREGROUND = "foreground"  # Run in foreground (for debugging)


class ParentStatus(Enum):
    """Status of the parent process."""
    ALIVE = "alive"
    DEAD = "dead"
    UNKNOWN = "unknown"


@dataclass
class ServiceConfig:
    """
    Configuration for the Selectron service.

    Attributes:
        mode: Operating mode (embedded, detached, foreground)
        parent_pid: PID of the parent process to monitor
        poll_interval: How often to check parent process (seconds)
        socket_path: Path for Unix socket IPC
        enable_execution_log: Enable execution logging for ML
        execution_log_path: Path to execution log file
    """
    mode: ServiceMode = ServiceMode.EMBEDDED
    parent_pid: Optional[int] = None
    poll_interval: float = 1.0
    socket_path: Optional[Path] = None
    enable_execution_log: bool = False
    execution_log_path: Optional[Path] = None

    def __post_init__(self):
        if self.socket_path is None:
            self.socket_path = Path.home() / ".selectron" / "selectron.sock"
        if self.execution_log_path is None:
            self.execution_log_path = Path.home() / ".selectron" / "execution.log"


class SelectronService:
    """
    Selectron service daemon.

    In embedded mode (current), this just ensures the monitor is running.
    Future versions will support detached mode for persistent session management.

    Example (embedded mode):
        service = SelectronService()
        service.start()
        # ... use Selectron normally ...
        service.stop()

    Example (future detached mode):
        config = ServiceConfig(mode=ServiceMode.DETACHED)
        service = SelectronService(config)
        service.start()  # Forks and runs in background
    """

    def __init__(self, config: Optional[ServiceConfig] = None):
        """
        Initialize the Selectron service.

        Args:
            config: Service configuration (uses defaults if not provided)
        """
        self._config = config or ServiceConfig()
        self._running = False
        self._parent_status = ParentStatus.UNKNOWN

    @property
    def is_running(self) -> bool:
        """Check if the service is running."""
        return self._running

    @property
    def config(self) -> ServiceConfig:
        """Get the service configuration."""
        return self._config

    def start(self) -> None:
        """
        Start the service.

        In embedded mode, ensures the process monitor is running.
        Other modes are not yet implemented.

        Raises:
            NotImplementedError: If mode is not EMBEDDED
        """
        if self._config.mode == ServiceMode.EMBEDDED:
            from .monitor import get_monitor
            get_monitor().start()
            self._running = True
        else:
            raise NotImplementedError(
                f"Service mode {self._config.mode.value} not yet implemented. "
                f"See roadmap for v0.4.0+."
            )

    def stop(self) -> None:
        """Stop the service."""
        if self._running:
            from .monitor import get_monitor
            get_monitor().stop()
            self._running = False

    def check_parent(self) -> ParentStatus:
        """
        Check if the parent process is still alive.

        Returns:
            ParentStatus indicating if parent is alive, dead, or unknown
        """
        if self._config.parent_pid is None:
            return ParentStatus.UNKNOWN

        try:
            # Send signal 0 to check if process exists
            os.kill(self._config.parent_pid, 0)
            self._parent_status = ParentStatus.ALIVE
        except OSError:
            self._parent_status = ParentStatus.DEAD

        return self._parent_status


# ============================================================================
# Execution Logging (Future - v0.5.0)
# ============================================================================

class ExecutionEventType(Enum):
    """Types of execution events for logging."""
    SESSION_START = "session_start"
    SESSION_STOP = "session_stop"
    COMMAND_SENT = "command_sent"
    RESPONSE_RECEIVED = "response_received"
    USER_ACTION = "user_action"
    ERROR = "error"
    CUSTOM = "custom"


@dataclass
class ExecutionLogEntry:
    """
    Log entry for execution events.

    Future use: Training data for ML models that learn from
    user interactions with Electron apps.

    Attributes:
        timestamp: When the event occurred
        session_id: Associated session ID
        app_name: Name of the Electron app
        event_type: Type of event
        payload: Event-specific data
        context: Additional context (e.g., current page, element)
        outcome: Result of the action (success, failure, etc.)
    """
    timestamp: datetime
    session_id: str
    app_name: str
    event_type: ExecutionEventType
    payload: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    outcome: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "app_name": self.app_name,
            "event_type": self.event_type.value,
            "payload": self.payload,
            "context": self.context,
            "outcome": self.outcome,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ExecutionLogEntry":
        """Deserialize from dictionary."""
        return cls(
            timestamp=datetime.fromisoformat(d["timestamp"]),
            session_id=d["session_id"],
            app_name=d["app_name"],
            event_type=ExecutionEventType(d["event_type"]),
            payload=d.get("payload", {}),
            context=d.get("context", {}),
            outcome=d.get("outcome"),
        )


class ExecutionLogger:
    """
    Logger for execution events.

    NOTE: This is a stub for future implementation.
    Full functionality planned for v0.5.0.

    Future features:
        - JSON-Lines file format for efficient appending
        - Log rotation and compression
        - Export to Parquet for ML training
        - Embedding-based query for similar examples
    """

    def __init__(self, log_path: Optional[Path] = None, enabled: bool = False):
        """
        Initialize the execution logger.

        Args:
            log_path: Path to the log file
            enabled: Whether logging is enabled
        """
        self._log_path = log_path or Path.home() / ".selectron" / "execution.jsonl"
        self._enabled = enabled
        self._entries: List[ExecutionLogEntry] = []

    @property
    def enabled(self) -> bool:
        """Check if logging is enabled."""
        return self._enabled

    def enable(self) -> None:
        """Enable logging."""
        self._enabled = True

    def disable(self) -> None:
        """Disable logging."""
        self._enabled = False

    def log(self, entry: ExecutionLogEntry) -> None:
        """
        Log an execution event.

        Args:
            entry: Event to log
        """
        if not self._enabled:
            return

        self._entries.append(entry)
        # Future: Write to file, implement rotation, etc.

    def log_event(
        self,
        session_id: str,
        app_name: str,
        event_type: ExecutionEventType,
        payload: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        outcome: Optional[str] = None,
    ) -> None:
        """
        Convenience method to log an event.

        Args:
            session_id: Associated session ID
            app_name: Name of the Electron app
            event_type: Type of event
            payload: Event-specific data
            context: Additional context
            outcome: Result of the action
        """
        entry = ExecutionLogEntry(
            timestamp=datetime.now(),
            session_id=session_id,
            app_name=app_name,
            event_type=event_type,
            payload=payload or {},
            context=context or {},
            outcome=outcome,
        )
        self.log(entry)

    def flush(self) -> None:
        """
        Flush pending log entries to disk.

        NOTE: Stub implementation - full version in v0.5.0.
        """
        pass  # Future: Write to JSONL file

    def query_similar(self, query: str, limit: int = 10) -> List[ExecutionLogEntry]:
        """
        Query for similar execution patterns using embeddings.

        NOTE: Stub implementation - full version in v0.5.0+.

        Args:
            query: Natural language query
            limit: Maximum number of results

        Returns:
            List of similar log entries
        """
        raise NotImplementedError(
            "Embedding-based query not yet implemented. "
            "Planned for future version."
        )
