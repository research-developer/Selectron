"""
Shared data types for the controller module.

These types are used across core and adapter layers.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional


class NotificationLevel(Enum):
    """Notification severity levels."""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    BLOCKED = "blocked"


@dataclass
class Notification:
    """A single notification."""
    id: str
    agent: str
    level: NotificationLevel
    summary: str
    context: str = ""
    action_hint: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    read: bool = False

    @property
    def icon(self) -> str:
        """Get emoji icon for this notification level."""
        icons = {
            NotificationLevel.INFO: "ℹ️",
            NotificationLevel.SUCCESS: "✅",
            NotificationLevel.WARNING: "⚠️",
            NotificationLevel.ERROR: "❌",
            NotificationLevel.BLOCKED: "🚫",
        }
        return icons.get(self.level, "📌")

    @property
    def color_name(self) -> str:
        """Get color name for this notification level (for UI mapping)."""
        colors = {
            NotificationLevel.INFO: "blue",
            NotificationLevel.SUCCESS: "green",
            NotificationLevel.WARNING: "yellow",
            NotificationLevel.ERROR: "red",
            NotificationLevel.BLOCKED: "magenta",
        }
        return colors.get(self.level, "white")


@dataclass
class Agent:
    """An agent in the system."""
    name: str
    session_id: str
    teams: List[str] = field(default_factory=list)
    is_processing: bool = False
    locked: bool = False
    locked_by: Optional[str] = None


@dataclass
class Team:
    """A team of agents."""
    name: str
    description: str = ""
    parent_team: Optional[str] = None
    members: List[str] = field(default_factory=list)


@dataclass
class MCPResponse:
    """Response from an MCP call."""
    success: bool
    data: Any = None
    error: Optional[str] = None
