#!/usr/bin/env python3
"""
iTerm MCP Client for live data integration.

Provides a Python interface to the iTerm MCP server for fetching
real-time agent, team, and notification data.
"""

import json
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime
from threading import Lock

from .notification_center import (
    Notification,
    NotificationLevel,
    Agent,
    Team,
)


@dataclass
class MCPResponse:
    """Response from an MCP call."""
    success: bool
    data: Any = None
    error: Optional[str] = None


class ITermMCPClient:
    """
    Client for communicating with the iTerm MCP server.

    This client provides methods to:
    - List and manage sessions
    - List and manage agents
    - List and manage teams
    - Send messages to sessions
    - Read session output
    - Get notifications

    In a real implementation, this would use the MCP protocol directly.
    For now, it uses subprocess calls to interact with the MCP server
    or returns cached/mock data when MCP is not available.
    """

    def __init__(self, cache_ttl: float = 5.0):
        """
        Initialize the MCP client.

        Args:
            cache_ttl: Time-to-live for cached data in seconds
        """
        self._cache: Dict[str, tuple] = {}  # key -> (data, timestamp)
        self._cache_ttl = cache_ttl
        self._lock = Lock()

        # Callbacks for real-time updates
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
        """
        List all iTerm sessions.

        Args:
            agents_only: If True, only return sessions with registered agents

        Returns:
            List of session dictionaries
        """
        cache_key = f"sessions_{agents_only}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        # This would call the MCP in real implementation
        # For now, return mock data
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
        """
        Create a new iTerm session.

        Args:
            name: Session name
            agent: Agent name to register
            team: Team to assign
            command: Initial command to run
            agent_type: AI agent type to launch (claude, gemini, etc.)

        Returns:
            MCPResponse with session_id on success
        """
        # This would call create_sessions MCP tool
        # For now, return mock success
        return MCPResponse(
            success=True,
            data={
                "session_id": "NEW-SESSION-ID",
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
        """
        Write content to a session.

        Args:
            content: Text to send
            session_id: Target session ID
            agent: Target agent name (alternative to session_id)
            execute: Whether to press Enter after sending

        Returns:
            MCPResponse indicating success/failure
        """
        # This would call write_to_sessions MCP tool
        return MCPResponse(success=True)

    def read_session(
        self,
        session_id: Optional[str] = None,
        agent: Optional[str] = None,
        max_lines: int = 50,
    ) -> MCPResponse:
        """
        Read output from a session.

        Args:
            session_id: Target session ID
            agent: Target agent name
            max_lines: Maximum lines to return

        Returns:
            MCPResponse with session content
        """
        # This would call read_sessions MCP tool
        return MCPResponse(
            success=True,
            data={
                "content": f"[Mock output for {agent or session_id}]",
                "line_count": 1,
            }
        )

    # === Agent Operations ===

    def list_agents(self, team: Optional[str] = None) -> List[Agent]:
        """
        List all registered agents.

        Args:
            team: Filter by team name

        Returns:
            List of Agent objects
        """
        cache_key = f"agents_{team}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        # Mock data - would call list_agents MCP tool
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
        """Register an agent for a session."""
        return MCPResponse(success=True)

    def remove_agent(self, agent_name: str) -> MCPResponse:
        """Remove an agent registration."""
        return MCPResponse(success=True)

    # === Team Operations ===

    def list_teams(self) -> List[Team]:
        """
        List all teams.

        Returns:
            List of Team objects
        """
        cached = self._get_cached("teams")
        if cached:
            return cached

        # Mock data - would call list_teams MCP tool
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
        """Create a new team."""
        self._clear_cache("teams")
        return MCPResponse(success=True)

    def assign_agent_to_team(self, agent_name: str, team_name: str) -> MCPResponse:
        """Add an agent to a team."""
        self._clear_cache()
        return MCPResponse(success=True)

    # === Notification Operations ===

    def get_notifications(
        self,
        agent: Optional[str] = None,
        level: Optional[str] = None,
        limit: int = 20,
    ) -> List[Notification]:
        """
        Get recent notifications.

        Args:
            agent: Filter by agent name
            level: Filter by level (info, warning, error, etc.)
            limit: Maximum notifications to return

        Returns:
            List of Notification objects
        """
        # Mock data - would call get_notifications MCP tool
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
        """Send a notification for an agent."""
        return MCPResponse(success=True)

    # === Session Control ===

    def focus_session(
        self,
        session_id: Optional[str] = None,
        agent: Optional[str] = None,
    ) -> MCPResponse:
        """Focus on a session (bring to foreground)."""
        return MCPResponse(success=True)

    def modify_session(
        self,
        session_id: Optional[str] = None,
        agent: Optional[str] = None,
        tab_color: Optional[Dict[str, int]] = None,
        badge: Optional[str] = None,
    ) -> MCPResponse:
        """Modify session appearance."""
        return MCPResponse(success=True)

    def send_control(
        self,
        control_char: str,
        session_id: Optional[str] = None,
        agent: Optional[str] = None,
    ) -> MCPResponse:
        """Send a control character (like Ctrl+C)."""
        return MCPResponse(success=True)


# Singleton instance
_client: Optional[ITermMCPClient] = None


def get_mcp_client() -> ITermMCPClient:
    """Get or create the singleton MCP client."""
    global _client
    if _client is None:
        _client = ITermMCPClient()
    return _client


def reset_mcp_client() -> None:
    """Reset the singleton MCP client."""
    global _client
    _client = None
