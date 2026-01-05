#!/usr/bin/env python3
"""
Team Window Manager for iTerm Agent Orchestration.

Groups agents by team into shared iTerm windows with configurable layouts.
Integrates with iTerm MCP tools for session management.
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Any
from threading import Lock

from ...core.menu import ANSI


class WindowLayout(Enum):
    """Window layout types for team sessions."""
    SINGLE = "SINGLE"
    HORIZONTAL_SPLIT = "HORIZONTAL_SPLIT"
    VERTICAL_SPLIT = "VERTICAL_SPLIT"
    QUAD = "QUAD"
    THREE_COLUMNS = "THREE_COLUMNS"
    THREE_ROWS = "THREE_ROWS"


@dataclass
class AgentSession:
    """An agent's iTerm session info."""
    name: str
    session_id: str
    team: Optional[str] = None
    window_id: Optional[str] = None
    role: Optional[str] = None
    is_highlighted: bool = False


@dataclass
class TeamWindow:
    """A team's iTerm window configuration."""
    team_name: str
    window_id: str
    layout: WindowLayout
    agents: List[AgentSession] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    @property
    def agent_count(self) -> int:
        return len(self.agents)

    @property
    def agent_names(self) -> List[str]:
        return [a.name for a in self.agents]


# Default highlight colors by role
ROLE_COLORS = {
    "builder": {"red": 100, "green": 200, "blue": 100},
    "tester": {"red": 100, "green": 150, "blue": 255},
    "debugger": {"red": 255, "green": 150, "blue": 100},
    "researcher": {"red": 200, "green": 100, "blue": 255},
    "devops": {"red": 255, "green": 200, "blue": 100},
    "orchestrator": {"red": 255, "green": 100, "blue": 150},
    "monitor": {"red": 100, "green": 255, "blue": 200},
    "default": {"red": 150, "green": 150, "blue": 150},
}

# Highlight color for focused agent
HIGHLIGHT_COLOR = {"red": 255, "green": 215, "blue": 0}  # Gold


class TeamWindowManager:
    """
    Manages iTerm windows organized by team.

    Groups agents into shared windows with configurable layouts (horizontal split,
    vertical split, quad, etc.). Provides visual feedback through tab colors and
    highlighting.

    Example usage:
        manager = TeamWindowManager()

        # Create a team window with agents
        await manager.create_team_window(
            "backend-team",
            agents=[
                {"name": "api-builder", "role": "builder"},
                {"name": "db-tester", "role": "tester"},
            ],
            layout=WindowLayout.HORIZONTAL_SPLIT
        )

        # Add another agent to the team
        await manager.add_agent_to_team_window("backend-team", {"name": "debugger-1"})

        # Focus and highlight
        await manager.focus_team("backend-team")
        await manager.highlight_agent("api-builder")
    """

    def __init__(self, mcp_client: Optional[Any] = None):
        """
        Initialize the TeamWindowManager.

        Args:
            mcp_client: Optional MCP client for iTerm communication.
                        If None, calls will be prepared but not executed.
        """
        self.mcp_client = mcp_client
        self._team_windows: Dict[str, TeamWindow] = {}
        self._agent_sessions: Dict[str, AgentSession] = {}
        self._lock = Lock()

        # Callbacks
        self._on_window_created: Optional[Callable[[TeamWindow], None]] = None
        self._on_agent_added: Optional[Callable[[str, AgentSession], None]] = None
        self._on_agent_highlighted: Optional[Callable[[AgentSession], None]] = None

    @property
    def teams(self) -> List[str]:
        """Get list of all team names."""
        return list(self._team_windows.keys())

    @property
    def windows(self) -> List[TeamWindow]:
        """Get list of all team windows."""
        return list(self._team_windows.values())

    def on_window_created(self, callback: Callable[[TeamWindow], None]) -> None:
        """Set callback for when a team window is created."""
        self._on_window_created = callback

    def on_agent_added(self, callback: Callable[[str, AgentSession], None]) -> None:
        """Set callback for when an agent is added to a team window."""
        self._on_agent_added = callback

    def on_agent_highlighted(self, callback: Callable[[AgentSession], None]) -> None:
        """Set callback for when an agent is highlighted."""
        self._on_agent_highlighted = callback

    def _select_layout(self, agent_count: int) -> WindowLayout:
        """Select optimal layout based on number of agents."""
        if agent_count <= 1:
            return WindowLayout.SINGLE
        elif agent_count == 2:
            return WindowLayout.HORIZONTAL_SPLIT
        elif agent_count == 3:
            return WindowLayout.THREE_COLUMNS
        elif agent_count == 4:
            return WindowLayout.QUAD
        else:
            # For more than 4, use QUAD and let extras stack
            return WindowLayout.QUAD

    async def create_team_window(
        self,
        team_name: str,
        agents: List[Dict[str, Any]],
        layout: Optional[WindowLayout] = None,
        window_id: Optional[str] = None,
    ) -> Optional[TeamWindow]:
        """
        Create a new iTerm window for a team with specified agents.

        Args:
            team_name: Name of the team
            agents: List of agent configs with 'name' and optional 'role', 'command'
            layout: Window layout (auto-selected if None)
            window_id: Existing window ID to use (creates new if None)

        Returns:
            TeamWindow if successful, None otherwise
        """
        if team_name in self._team_windows:
            print(f"{ANSI.YELLOW}Team '{team_name}' already has a window{ANSI.RESET}")
            return self._team_windows[team_name]

        # Select layout if not specified
        if layout is None:
            layout = self._select_layout(len(agents))

        # Build session configs for MCP create_sessions
        session_configs = []
        for agent in agents:
            config = {
                "name": f"{team_name}-{agent['name']}",
                "agent": agent["name"],
                "team": team_name,
            }
            if "role" in agent:
                config["role"] = agent["role"]
            if "command" in agent:
                config["command"] = agent["command"]
            if "agent_type" in agent:
                config["agent_type"] = agent["agent_type"]
            session_configs.append(config)

        # Prepare MCP request
        mcp_request = {
            "sessions": session_configs,
            "layout": layout.value,
        }
        if window_id:
            mcp_request["window_id"] = window_id

        # Execute MCP call if client available
        result_window_id = window_id or f"team-{team_name}-{int(time.time())}"
        created_sessions = []

        if self.mcp_client:
            try:
                result = await self.mcp_client.create_sessions(mcp_request)
                if result and "sessions" in result:
                    for sess in result["sessions"]:
                        created_sessions.append(AgentSession(
                            name=sess.get("agent", sess["name"]),
                            session_id=sess["session_id"],
                            team=team_name,
                            window_id=sess.get("window_id", result_window_id),
                            role=sess.get("role"),
                        ))
                    result_window_id = result.get("window_id", result_window_id)
            except Exception as e:
                print(f"{ANSI.RED}Error creating team window: {e}{ANSI.RESET}")
                return None
        else:
            # Mock sessions for testing without MCP
            for i, agent in enumerate(agents):
                created_sessions.append(AgentSession(
                    name=agent["name"],
                    session_id=f"mock-{team_name}-{i}",
                    team=team_name,
                    window_id=result_window_id,
                    role=agent.get("role"),
                ))

        # Create TeamWindow record
        team_window = TeamWindow(
            team_name=team_name,
            window_id=result_window_id,
            layout=layout,
            agents=created_sessions,
        )

        # Store references
        with self._lock:
            self._team_windows[team_name] = team_window
            for agent_session in created_sessions:
                self._agent_sessions[agent_session.name] = agent_session

        # Apply role-based tab colors
        await self._apply_team_colors(team_window)

        # Callback
        if self._on_window_created:
            self._on_window_created(team_window)

        print(f"{ANSI.GREEN}Created team window '{team_name}' with {len(created_sessions)} agents{ANSI.RESET}")
        return team_window

    async def add_agent_to_team_window(
        self,
        team_name: str,
        agent: Dict[str, Any],
    ) -> Optional[AgentSession]:
        """
        Add an agent to an existing team window.

        Args:
            team_name: Name of the team
            agent: Agent config with 'name' and optional 'role', 'command'

        Returns:
            AgentSession if successful, None otherwise
        """
        if team_name not in self._team_windows:
            print(f"{ANSI.RED}Team '{team_name}' does not have a window{ANSI.RESET}")
            return None

        team_window = self._team_windows[team_name]

        # Check if agent already in team
        if agent["name"] in team_window.agent_names:
            print(f"{ANSI.YELLOW}Agent '{agent['name']}' already in team '{team_name}'{ANSI.RESET}")
            return self._agent_sessions.get(agent["name"])

        # Build session config
        session_config = {
            "name": f"{team_name}-{agent['name']}",
            "agent": agent["name"],
            "team": team_name,
        }
        if "role" in agent:
            session_config["role"] = agent["role"]
        if "command" in agent:
            session_config["command"] = agent["command"]
        if "agent_type" in agent:
            session_config["agent_type"] = agent["agent_type"]

        # Prepare MCP request - add to existing window
        mcp_request = {
            "sessions": [session_config],
            "layout": "VERTICAL_SPLIT",  # Split from existing
            "window_id": team_window.window_id,
        }

        # Execute MCP call if client available
        new_session = None

        if self.mcp_client:
            try:
                result = await self.mcp_client.create_sessions(mcp_request)
                if result and "sessions" in result and result["sessions"]:
                    sess = result["sessions"][0]
                    new_session = AgentSession(
                        name=sess.get("agent", agent["name"]),
                        session_id=sess["session_id"],
                        team=team_name,
                        window_id=team_window.window_id,
                        role=sess.get("role", agent.get("role")),
                    )
            except Exception as e:
                print(f"{ANSI.RED}Error adding agent to team: {e}{ANSI.RESET}")
                return None
        else:
            # Mock session for testing
            new_session = AgentSession(
                name=agent["name"],
                session_id=f"mock-{team_name}-{len(team_window.agents)}",
                team=team_name,
                window_id=team_window.window_id,
                role=agent.get("role"),
            )

        if new_session:
            with self._lock:
                team_window.agents.append(new_session)
                self._agent_sessions[new_session.name] = new_session

            # Apply color for new agent
            await self._apply_agent_color(new_session)

            # Callback
            if self._on_agent_added:
                self._on_agent_added(team_name, new_session)

            print(f"{ANSI.GREEN}Added agent '{agent['name']}' to team '{team_name}'{ANSI.RESET}")

        return new_session

    def get_team_window(self, team_name: str) -> Optional[str]:
        """
        Get the window_id for a team.

        Args:
            team_name: Name of the team

        Returns:
            window_id if team has a window, None otherwise
        """
        team_window = self._team_windows.get(team_name)
        return team_window.window_id if team_window else None

    def get_team_info(self, team_name: str) -> Optional[TeamWindow]:
        """
        Get full TeamWindow info for a team.

        Args:
            team_name: Name of the team

        Returns:
            TeamWindow if exists, None otherwise
        """
        return self._team_windows.get(team_name)

    def get_agent_session(self, agent_name: str) -> Optional[AgentSession]:
        """
        Get session info for an agent.

        Args:
            agent_name: Name of the agent

        Returns:
            AgentSession if found, None otherwise
        """
        return self._agent_sessions.get(agent_name)

    async def focus_team(self, team_name: str) -> bool:
        """
        Bring team window to front and focus it.

        Args:
            team_name: Name of the team to focus

        Returns:
            True if successful, False otherwise
        """
        team_window = self._team_windows.get(team_name)
        if not team_window:
            print(f"{ANSI.RED}Team '{team_name}' not found{ANSI.RESET}")
            return False

        if self.mcp_client:
            try:
                # Focus on first agent's session in the team
                if team_window.agents:
                    first_agent = team_window.agents[0]
                    await self.mcp_client.set_active_session({
                        "agent": first_agent.name,
                        "focus": True,
                    })
                    print(f"{ANSI.GREEN}Focused on team '{team_name}'{ANSI.RESET}")
                    return True
            except Exception as e:
                print(f"{ANSI.RED}Error focusing team: {e}{ANSI.RESET}")
                return False
        else:
            print(f"{ANSI.CYAN}[Mock] Would focus team '{team_name}'{ANSI.RESET}")
            return True

        return False

    async def highlight_agent(
        self,
        agent_name: str,
        duration: Optional[float] = None,
    ) -> bool:
        """
        Visually highlight an agent's session.

        Args:
            agent_name: Name of the agent to highlight
            duration: How long to highlight (None = permanent until unhighlighted)

        Returns:
            True if successful, False otherwise
        """
        agent = self._agent_sessions.get(agent_name)
        if not agent:
            print(f"{ANSI.RED}Agent '{agent_name}' not found{ANSI.RESET}")
            return False

        # Clear previous highlight in same team
        if agent.team:
            team_window = self._team_windows.get(agent.team)
            if team_window:
                for other_agent in team_window.agents:
                    if other_agent.is_highlighted and other_agent.name != agent_name:
                        await self._unhighlight_agent(other_agent)

        # Apply highlight
        if self.mcp_client:
            try:
                modifications = [{
                    "agent": agent_name,
                    "tab_color": HIGHLIGHT_COLOR,
                    "tab_color_enabled": True,
                    "focus": True,
                    "set_active": True,
                    "badge": f">>> {agent_name} <<<",
                }]
                await self.mcp_client.modify_sessions({"modifications": modifications})
                agent.is_highlighted = True

                # Callback
                if self._on_agent_highlighted:
                    self._on_agent_highlighted(agent)

                print(f"{ANSI.YELLOW}Highlighted agent '{agent_name}'{ANSI.RESET}")

                # Auto-unhighlight after duration
                if duration:
                    asyncio.create_task(self._delayed_unhighlight(agent, duration))

                return True
            except Exception as e:
                print(f"{ANSI.RED}Error highlighting agent: {e}{ANSI.RESET}")
                return False
        else:
            agent.is_highlighted = True
            print(f"{ANSI.CYAN}[Mock] Would highlight agent '{agent_name}'{ANSI.RESET}")
            return True

    async def unhighlight_agent(self, agent_name: str) -> bool:
        """
        Remove highlight from an agent's session.

        Args:
            agent_name: Name of the agent to unhighlight

        Returns:
            True if successful, False otherwise
        """
        agent = self._agent_sessions.get(agent_name)
        if not agent:
            return False

        return await self._unhighlight_agent(agent)

    async def _unhighlight_agent(self, agent: AgentSession) -> bool:
        """Internal unhighlight implementation."""
        if self.mcp_client:
            try:
                # Restore role color or reset
                color = ROLE_COLORS.get(agent.role, ROLE_COLORS["default"])
                modifications = [{
                    "agent": agent.name,
                    "tab_color": color,
                    "badge": agent.name,
                }]
                await self.mcp_client.modify_sessions({"modifications": modifications})
                agent.is_highlighted = False
                return True
            except Exception:
                return False
        else:
            agent.is_highlighted = False
            return True

    async def _delayed_unhighlight(self, agent: AgentSession, duration: float) -> None:
        """Unhighlight after a delay."""
        await asyncio.sleep(duration)
        if agent.is_highlighted:
            await self._unhighlight_agent(agent)

    async def _apply_team_colors(self, team_window: TeamWindow) -> None:
        """Apply role-based colors to all agents in a team."""
        for agent in team_window.agents:
            await self._apply_agent_color(agent)

    async def _apply_agent_color(self, agent: AgentSession) -> None:
        """Apply role-based color to an agent's session."""
        if not self.mcp_client:
            return

        color = ROLE_COLORS.get(agent.role, ROLE_COLORS["default"])

        try:
            modifications = [{
                "agent": agent.name,
                "tab_color": color,
                "tab_color_enabled": True,
                "badge": agent.name,
            }]
            await self.mcp_client.modify_sessions({"modifications": modifications})
        except Exception as e:
            print(f"{ANSI.DIM}Warning: Could not apply color to {agent.name}: {e}{ANSI.RESET}")

    async def remove_agent(self, agent_name: str) -> bool:
        """
        Remove an agent from its team window.

        Note: This removes tracking only. The iTerm session continues to exist.

        Args:
            agent_name: Name of the agent to remove

        Returns:
            True if successful, False otherwise
        """
        agent = self._agent_sessions.get(agent_name)
        if not agent:
            return False

        # Remove from team window
        if agent.team and agent.team in self._team_windows:
            team_window = self._team_windows[agent.team]
            team_window.agents = [a for a in team_window.agents if a.name != agent_name]

        # Remove from tracking
        with self._lock:
            del self._agent_sessions[agent_name]

        print(f"{ANSI.YELLOW}Removed agent '{agent_name}' from tracking{ANSI.RESET}")
        return True

    async def close_team_window(self, team_name: str) -> bool:
        """
        Close a team window and remove all agents.

        Note: This removes tracking. Actual session closure depends on MCP support.

        Args:
            team_name: Name of the team

        Returns:
            True if successful, False otherwise
        """
        team_window = self._team_windows.get(team_name)
        if not team_window:
            return False

        # Remove all agent tracking
        for agent in team_window.agents:
            if agent.name in self._agent_sessions:
                del self._agent_sessions[agent.name]

        # Remove team window
        with self._lock:
            del self._team_windows[team_name]

        print(f"{ANSI.YELLOW}Closed team window '{team_name}'{ANSI.RESET}")
        return True

    def list_teams(self) -> None:
        """Print a summary of all team windows."""
        if not self._team_windows:
            print(f"{ANSI.DIM}No team windows{ANSI.RESET}")
            return

        print(f"\n{ANSI.BOLD}Team Windows:{ANSI.RESET}")
        print("=" * 50)
        for team_name, team_window in self._team_windows.items():
            print(f"\n{ANSI.CYAN}{team_name}{ANSI.RESET} ({team_window.layout.value})")
            print(f"  Window ID: {team_window.window_id}")
            print(f"  Agents ({len(team_window.agents)}):")
            for agent in team_window.agents:
                highlight = " *" if agent.is_highlighted else ""
                role = f" [{agent.role}]" if agent.role else ""
                print(f"    - {agent.name}{role}{highlight}")
        print()


def create_team_window_manager(mcp_client: Optional[Any] = None) -> TeamWindowManager:
    """Create a configured TeamWindowManager."""
    return TeamWindowManager(mcp_client=mcp_client)


async def demo():
    """Demo of TeamWindowManager functionality."""
    print("TeamWindowManager Demo")
    print("=" * 40)

    manager = TeamWindowManager()

    # Create a team window
    print("\n1. Creating backend team window...")
    await manager.create_team_window(
        "backend-team",
        agents=[
            {"name": "api-builder", "role": "builder"},
            {"name": "db-tester", "role": "tester"},
            {"name": "cache-devops", "role": "devops"},
        ],
        layout=WindowLayout.THREE_COLUMNS,
    )

    # Create another team
    print("\n2. Creating frontend team window...")
    await manager.create_team_window(
        "frontend-team",
        agents=[
            {"name": "ui-builder", "role": "builder"},
            {"name": "e2e-tester", "role": "tester"},
        ],
        layout=WindowLayout.HORIZONTAL_SPLIT,
    )

    # Add agent to team
    print("\n3. Adding debugger to backend team...")
    await manager.add_agent_to_team_window(
        "backend-team",
        {"name": "backend-debugger", "role": "debugger"},
    )

    # Get team info
    print("\n4. Getting team window ID...")
    window_id = manager.get_team_window("backend-team")
    print(f"   Backend team window: {window_id}")

    # Focus team
    print("\n5. Focusing backend team...")
    await manager.focus_team("backend-team")

    # Highlight agent
    print("\n6. Highlighting api-builder...")
    await manager.highlight_agent("api-builder")

    # List all teams
    print("\n7. Listing all teams...")
    manager.list_teams()

    print("\nDemo complete!")


if __name__ == "__main__":
    asyncio.run(demo())
