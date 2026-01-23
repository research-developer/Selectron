"""
Abstract interfaces for the controller module.

Defines protocols that adapters must implement, enabling
different backends (iTerm, VS Code, etc.) to be swapped.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

from .types import Agent, MCPResponse, Notification, NotificationLevel, Team


@runtime_checkable
class AgentClient(Protocol):
    """
    Protocol for agent client implementations.

    This defines the interface that all agent clients must implement,
    whether for iTerm MCP, VS Code, or mock testing.
    """

    # === Session Operations ===

    def list_sessions(self, agents_only: bool = False) -> List[Dict[str, Any]]:
        """List all terminal sessions."""
        ...

    def create_session(
        self,
        name: str,
        agent: Optional[str] = None,
        team: Optional[str] = None,
        command: Optional[str] = None,
        agent_type: Optional[str] = None,
    ) -> MCPResponse:
        """Create a new terminal session."""
        ...

    def write_to_session(
        self,
        content: str,
        session_id: Optional[str] = None,
        agent: Optional[str] = None,
        execute: bool = True,
    ) -> MCPResponse:
        """Write content to a session."""
        ...

    def read_session(
        self,
        session_id: Optional[str] = None,
        agent: Optional[str] = None,
        max_lines: int = 50,
    ) -> MCPResponse:
        """Read output from a session."""
        ...

    def focus_session(
        self,
        session_id: Optional[str] = None,
        agent: Optional[str] = None,
    ) -> MCPResponse:
        """Focus on a session (bring to foreground)."""
        ...

    def modify_session(
        self,
        session_id: Optional[str] = None,
        agent: Optional[str] = None,
        tab_color: Optional[Dict[str, int]] = None,
        badge: Optional[str] = None,
    ) -> MCPResponse:
        """Modify session appearance."""
        ...

    def send_control(
        self,
        control_char: str,
        session_id: Optional[str] = None,
        agent: Optional[str] = None,
    ) -> MCPResponse:
        """Send a control character (like Ctrl+C)."""
        ...

    # === Agent Operations ===

    def list_agents(self, team: Optional[str] = None) -> List[Agent]:
        """List all registered agents."""
        ...

    def register_agent(
        self,
        name: str,
        session_id: str,
        teams: Optional[List[str]] = None,
    ) -> MCPResponse:
        """Register an agent for a session."""
        ...

    def remove_agent(self, agent_name: str) -> MCPResponse:
        """Remove an agent registration."""
        ...

    # === Team Operations ===

    def list_teams(self) -> List[Team]:
        """List all teams."""
        ...

    def create_team(
        self,
        name: str,
        description: str = "",
        parent_team: Optional[str] = None,
    ) -> MCPResponse:
        """Create a new team."""
        ...

    def assign_agent_to_team(self, agent_name: str, team_name: str) -> MCPResponse:
        """Add an agent to a team."""
        ...

    # === Notification Operations ===

    def get_notifications(
        self,
        agent: Optional[str] = None,
        level: Optional[str] = None,
        limit: int = 20,
    ) -> List[Notification]:
        """Get recent notifications."""
        ...

    def send_notification(
        self,
        agent: str,
        level: str,
        summary: str,
        context: str = "",
    ) -> MCPResponse:
        """Send a notification for an agent."""
        ...


@runtime_checkable
class AgentClientAsync(Protocol):
    """
    Async protocol for batch/complex operations.

    These methods are used by TeamWindowManager for operations
    that may take longer or need to be awaited.
    """

    async def create_sessions(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Create multiple sessions with layout configuration."""
        ...

    async def set_active_session(self, request: Dict[str, Any]) -> None:
        """Set the active session with focus."""
        ...

    async def modify_sessions(self, request: Dict[str, Any]) -> None:
        """Modify multiple sessions at once."""
        ...


class AnswerGenerator(ABC):
    """
    Abstract base class for AI answer generators.

    Used by ChoiceEngine to generate answer choices.
    """

    @abstractmethod
    async def generate_choices(
        self,
        prompt: str,
        count: int = 4,
        context: Optional[str] = None,
    ) -> List[str]:
        """Generate multiple answer choices for a prompt."""
        pass

    @abstractmethod
    async def generate_variants(
        self,
        original: str,
        prompt: str,
        count: int = 4,
        context: Optional[str] = None,
    ) -> List[str]:
        """Generate variants of an existing answer."""
        pass


class MockAgentClient:
    """
    Mock implementation of AgentClient for testing without iTerm.

    Provides sample data for development and testing purposes.
    """

    def __init__(self, cache_ttl: float = 5.0):
        """Initialize with optional cache TTL."""
        self._cache: Dict[str, tuple] = {}
        self._cache_ttl = cache_ttl
        self._lock = Lock()
        self._on_notification: Optional[Callable[[Notification], None]] = None
        self._on_agent_change: Optional[Callable[[Agent], None]] = None

    def _get_cached(self, key: str) -> Optional[Any]:
        """Get cached data if still valid."""
        with self._lock:
            if key in self._cache:
                data, timestamp = self._cache[key]
                if (datetime.now() - timestamp).total_seconds() < self._cache_ttl:
                    return data
        return None

    def _set_cached(self, key: str, data: Any) -> None:
        """Cache data with current timestamp."""
        with self._lock:
            self._cache[key] = (data, datetime.now())

    def _clear_cache(self, key: Optional[str] = None) -> None:
        """Clear cache for a key or all keys."""
        with self._lock:
            if key:
                self._cache.pop(key, None)
            else:
                self._cache.clear()

    # === Session Operations ===

    def list_sessions(self, agents_only: bool = False) -> List[Dict[str, Any]]:
        """List mock sessions."""
        cache_key = f"sessions_{agents_only}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        sessions = [
            {
                "session_id": "55FBCC14-A3B2-4502-815B-51ED1EF61A39",
                "name": "morpholint-orchestrator",
                "agent": "morpholint-lead",
                "team": "morpholint",
                "teams": ["morpholint"],
                "is_processing": False,
                "locked": False,
            },
            {
                "session_id": "84A3FDE0-A94F-4B23-ADB4-66DEE80AEA27",
                "name": "MorphoLint Implementation",
                "agent": "alpha",
                "team": None,
                "teams": [],
                "is_processing": True,
                "locked": False,
            },
            {
                "session_id": "7E700876-521A-4A64-B9E7-3CAEB01EFBDD",
                "name": "MorphoLint Implementation",
                "agent": "beta",
                "team": None,
                "teams": [],
                "is_processing": False,
                "locked": False,
            },
            {
                "session_id": "91B4B9F3-1803-48C6-B6E8-C03253EBCB9F",
                "name": "github-researcher",
                "agent": "github-researcher",
                "team": "orchestration-research",
                "teams": ["orchestration-research"],
                "is_processing": False,
                "locked": False,
            },
        ]

        if agents_only:
            sessions = [s for s in sessions if s.get("agent")]

        self._set_cached(cache_key, sessions)
        return sessions

    def create_session(
        self,
        name: str,
        agent: Optional[str] = None,
        team: Optional[str] = None,
        command: Optional[str] = None,
        agent_type: Optional[str] = None,
    ) -> MCPResponse:
        """Create a mock session."""
        return MCPResponse(
            success=True,
            data={
                "session_id": "MOCK-SESSION-ID",
                "name": name,
                "agent": agent,
            }
        )

    def write_to_session(
        self,
        content: str,
        session_id: Optional[str] = None,
        agent: Optional[str] = None,
        execute: bool = True,
    ) -> MCPResponse:
        """Mock write to session."""
        return MCPResponse(success=True)

    def read_session(
        self,
        session_id: Optional[str] = None,
        agent: Optional[str] = None,
        max_lines: int = 50,
    ) -> MCPResponse:
        """Mock read from session."""
        return MCPResponse(
            success=True,
            data={
                "content": f"[Mock output for {agent or session_id}]",
                "line_count": 1,
            }
        )

    def focus_session(
        self,
        session_id: Optional[str] = None,
        agent: Optional[str] = None,
    ) -> MCPResponse:
        """Mock focus session."""
        return MCPResponse(success=True)

    def modify_session(
        self,
        session_id: Optional[str] = None,
        agent: Optional[str] = None,
        tab_color: Optional[Dict[str, int]] = None,
        badge: Optional[str] = None,
    ) -> MCPResponse:
        """Mock modify session."""
        return MCPResponse(success=True)

    def send_control(
        self,
        control_char: str,
        session_id: Optional[str] = None,
        agent: Optional[str] = None,
    ) -> MCPResponse:
        """Mock send control character."""
        return MCPResponse(success=True)

    # === Agent Operations ===

    def list_agents(self, team: Optional[str] = None) -> List[Agent]:
        """List mock agents."""
        cache_key = f"agents_{team}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        agents = [
            Agent("morpholint-lead", "55FBCC14", ["morpholint"]),
            Agent("alpha", "84A3FDE0", []),
            Agent("beta", "7E700876", []),
            Agent("gamma", "F365CFB8", []),
            Agent("delta", "25DED406", []),
            Agent("github-researcher", "91B4B9F3", ["orchestration-research"]),
            Agent("pypi-researcher", "94E72346", ["orchestration-research"]),
            Agent("comparison-researcher", "46C5157D", ["orchestration-research"]),
            Agent("gamepad-demo", "BCBC6F42", []),
            Agent("controller-dev", "7C43A28A", ["selectron-dev"]),
        ]

        if team:
            agents = [a for a in agents if team in a.teams]

        self._set_cached(cache_key, agents)
        return agents

    def register_agent(
        self,
        name: str,
        session_id: str,
        teams: Optional[List[str]] = None,
    ) -> MCPResponse:
        """Mock register agent."""
        return MCPResponse(success=True)

    def remove_agent(self, agent_name: str) -> MCPResponse:
        """Mock remove agent."""
        return MCPResponse(success=True)

    # === Team Operations ===

    def list_teams(self) -> List[Team]:
        """List mock teams."""
        cached = self._get_cached("teams")
        if cached:
            return cached

        teams = [
            Team("orchestration-research", "Multi-agent orchestration patterns"),
            Team("morpholint", "MorphoLint linting tool"),
            Team("docs-testing", "Documentation testing"),
            Team("selectron-dev", "Selectron development"),
            Team("duality-validation", "Duality theory validation"),
        ]

        self._set_cached("teams", teams)
        return teams

    def create_team(
        self,
        name: str,
        description: str = "",
        parent_team: Optional[str] = None,
    ) -> MCPResponse:
        """Mock create team."""
        self._clear_cache("teams")
        return MCPResponse(success=True)

    def assign_agent_to_team(self, agent_name: str, team_name: str) -> MCPResponse:
        """Mock assign agent to team."""
        self._clear_cache()
        return MCPResponse(success=True)

    # === Notification Operations ===

    def get_notifications(
        self,
        agent: Optional[str] = None,
        level: Optional[str] = None,
        limit: int = 20,
    ) -> List[Notification]:
        """Get mock notifications."""
        notifications = [
            Notification(
                id="1",
                agent="morpholint-lead",
                level=NotificationLevel.SUCCESS,
                summary="Build completed successfully",
                context="All 42 tests passed",
            ),
            Notification(
                id="2",
                agent="github-researcher",
                level=NotificationLevel.INFO,
                summary="Found 3 relevant repositories",
            ),
            Notification(
                id="3",
                agent="alpha",
                level=NotificationLevel.WARNING,
                summary="Rate limit approaching",
                context="API calls: 450/500",
            ),
        ]

        if agent:
            notifications = [n for n in notifications if n.agent == agent]
        if level:
            notifications = [n for n in notifications if n.level.value == level]

        return notifications[:limit]

    def send_notification(
        self,
        agent: str,
        level: str,
        summary: str,
        context: str = "",
    ) -> MCPResponse:
        """Mock send notification."""
        return MCPResponse(success=True)

    # === Async Operations (for TeamWindowManager compatibility) ===

    async def create_sessions(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Mock create multiple sessions."""
        return {
            "sessions": [
                {"session_id": f"MOCK-{i}", "name": f"mock-session-{i}"}
                for i in range(len(request.get("sessions", [])))
            ]
        }

    async def set_active_session(self, request: Dict[str, Any]) -> None:
        """Mock set active session."""
        pass

    async def modify_sessions(self, request: Dict[str, Any]) -> None:
        """Mock modify multiple sessions."""
        pass
