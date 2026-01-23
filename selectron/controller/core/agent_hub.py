#!/usr/bin/env python3
"""
Agent Hub - Unified Agent Communication Platform.

Provides a central interface for interacting with all agents across teams,
with gamepad control and notification center integration.
"""

import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Dict, List, Optional
from threading import Event, Thread, Lock
from datetime import datetime

from .emulator import GamepadEmulator, GamepadButton
from .notification_center import create_notification_center
from .menu import GamepadMenu, MenuOption, MenuResult, ANSI
from ..types import Notification, Team


class MessageType(Enum):
    """Types of messages that can be sent."""
    COMMAND = auto()      # Execute a command
    PROMPT = auto()       # Send a prompt/instruction
    SIGNAL = auto()       # Control signal (interrupt, etc.)
    BROADCAST = auto()    # Team broadcast


@dataclass
class AgentMessage:
    """A message to/from an agent."""
    agent: str
    content: str
    message_type: MessageType = MessageType.PROMPT
    timestamp: datetime = field(default_factory=datetime.now)
    delivered: bool = False
    response: Optional[str] = None


@dataclass
class AgentStatus:
    """Current status of an agent."""
    name: str
    session_id: str
    teams: List[str]
    is_processing: bool = False
    locked: bool = False
    locked_by: Optional[str] = None
    last_output: str = ""
    last_activity: Optional[datetime] = None


class AgentHub:
    """
    Central hub for agent communication and control.

    Features:
    - Real-time agent/team listing from iTerm MCP
    - Send messages to individual agents or teams
    - Read agent output
    - Focus/switch to agent sessions
    - Notification center integration
    - Gamepad controls

    Controller Layout:
    ┌─────────────────────────────────────────────────┐
    │  LT: Quick Message    LB: Prev Agent    RB: Next Agent    RT: Team Broadcast  │
    ├─────────────────────────────────────────────────┤
    │     D-pad: Navigate                    Y: Read Output     │
    │                                        X: Send Command    │
    │     L-Stick: Scroll                    B: Back            │
    │                                        A: Select/Focus    │
    ├─────────────────────────────────────────────────┤
    │  SELECT: Show Teams    HOME: Notification Center    START: Quick Actions      │
    └─────────────────────────────────────────────────┘
    """

    def __init__(
        self,
        gamepad: Optional[GamepadEmulator] = None,
        auto_refresh: bool = True,
        refresh_interval: float = 5.0,
    ):
        # Create or use provided gamepad
        self.gamepad = gamepad or GamepadEmulator("Agent Hub")

        # Data stores
        self._agents: Dict[str, AgentStatus] = {}
        self._teams: Dict[str, Team] = {}
        self._current_agent: Optional[str] = None
        self._current_team: Optional[str] = None

        # Message history
        self._message_history: List[AgentMessage] = []

        # Notification center
        self.notification_center = create_notification_center(self.gamepad)

        # Menu for selections
        self._menu = GamepadMenu(self.gamepad)

        # State
        self._lock = Lock()
        self._running = False
        self._auto_refresh = auto_refresh
        self._refresh_interval = refresh_interval
        self._refresh_thread: Optional[Thread] = None
        self._stop_event = Event()

        # Callbacks
        self._on_agent_output: Optional[Callable[[str, str], None]] = None
        self._on_notification: Optional[Callable[[Notification], None]] = None

    @property
    def agents(self) -> List[AgentStatus]:
        """Get list of all agents."""
        return list(self._agents.values())

    @property
    def teams(self) -> List[Team]:
        """Get list of all teams."""
        return list(self._teams.values())

    @property
    def current_agent(self) -> Optional[AgentStatus]:
        """Get currently focused agent."""
        if self._current_agent:
            return self._agents.get(self._current_agent)
        return None

    def start(self) -> None:
        """Start the agent hub."""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()

        # Initial data fetch
        self.refresh()

        # Set up gamepad bindings
        self._setup_gamepad_bindings()

        # Start auto-refresh
        if self._auto_refresh:
            self._start_refresh_thread()

        print(f"{ANSI.GREEN}Agent Hub started{ANSI.RESET}")

    def stop(self) -> None:
        """Stop the agent hub."""
        self._running = False
        self._stop_event.set()

        if self._refresh_thread:
            self._refresh_thread.join(timeout=2)

        print(f"{ANSI.YELLOW}Agent Hub stopped{ANSI.RESET}")

    def refresh(self) -> None:
        """Refresh agent and team data from iTerm MCP."""
        self._fetch_agents()
        self._fetch_teams()
        self._fetch_notifications()

    def _fetch_agents(self) -> None:
        """Fetch agents from iTerm MCP."""
        # In a real implementation, this would call the MCP
        # For now, simulate with mock data based on actual MCP response
        mock_agents = [
            AgentStatus("morpholint-lead", "55FBCC14", ["morpholint"]),
            AgentStatus("alpha", "84A3FDE0", []),
            AgentStatus("beta", "7E700876", []),
            AgentStatus("gamma", "F365CFB8", []),
            AgentStatus("delta", "25DED406", []),
            AgentStatus("github-researcher", "91B4B9F3", ["orchestration-research"]),
            AgentStatus("pypi-researcher", "94E72346", ["orchestration-research"]),
            AgentStatus("comparison-researcher", "46C5157D", ["orchestration-research"]),
            AgentStatus("gamepad-demo", "BCBC6F42", []),
            AgentStatus("webber", "31AAF31F", ["sltt-research"]),
        ]

        with self._lock:
            self._agents = {a.name: a for a in mock_agents}

    def _fetch_teams(self) -> None:
        """Fetch teams from iTerm MCP."""
        mock_teams = [
            Team("orchestration-research", "Multi-agent orchestration patterns"),
            Team("morpholint", "MorphoLint linting tool"),
            Team("docs-testing", "Documentation testing"),
            Team("sltt-research", "SLTT research"),
        ]

        with self._lock:
            self._teams = {t.name: t for t in mock_teams}

    def _fetch_notifications(self) -> None:
        """Fetch notifications from iTerm MCP."""
        # Update notification center with latest data
        pass

    def _start_refresh_thread(self) -> None:
        """Start background refresh thread."""
        def refresh_loop():
            while not self._stop_event.wait(self._refresh_interval):
                if self._running:
                    self.refresh()

        self._refresh_thread = Thread(target=refresh_loop, daemon=True)
        self._refresh_thread.start()

    def _setup_gamepad_bindings(self) -> None:
        """Set up gamepad button bindings."""

        def on_button(button: GamepadButton, pressed: bool):
            if not pressed or self.notification_center.is_open:
                return

            if button == GamepadButton.A:
                self._focus_current_agent()
            elif button == GamepadButton.B:
                self._go_back()
            elif button == GamepadButton.X:
                self._send_command_prompt()
            elif button == GamepadButton.Y:
                self._read_current_output()
            elif button == GamepadButton.LB:
                self._prev_agent()
            elif button == GamepadButton.RB:
                self._next_agent()
            elif button == GamepadButton.LT:
                self._quick_message()
            elif button == GamepadButton.RT:
                self._team_broadcast()
            elif button == GamepadButton.SELECT:
                self._show_teams()
            elif button == GamepadButton.START:
                self._show_quick_actions()

        self.gamepad.on_button(on_button)

    # === Agent Operations ===

    def select_agent(self, agent_name: str) -> bool:
        """Select an agent as the current focus."""
        if agent_name in self._agents:
            self._current_agent = agent_name
            return True
        return False

    def get_agent_output(self, agent_name: str, max_lines: int = 50) -> str:
        """Get recent output from an agent."""
        agent = self._agents.get(agent_name)
        if not agent:
            return ""

        # This would call read_sessions in real implementation
        return f"[Output from {agent_name}]\n(mock output - would fetch from iTerm MCP)"

    def send_to_agent(
        self,
        agent_name: str,
        message: str,
        message_type: MessageType = MessageType.PROMPT,
        execute: bool = True,
    ) -> bool:
        """Send a message to an agent."""
        agent = self._agents.get(agent_name)
        if not agent:
            return False

        msg = AgentMessage(
            agent=agent_name,
            content=message,
            message_type=message_type,
        )

        # This would call write_to_sessions in real implementation
        # For now, just record the message
        self._message_history.append(msg)
        msg.delivered = True

        print(f"{ANSI.GREEN}Sent to {agent_name}: {message[:50]}...{ANSI.RESET}")
        return True

    def broadcast_to_team(self, team_name: str, message: str) -> int:
        """Broadcast a message to all agents in a team."""
        team = self._teams.get(team_name)
        if not team:
            return 0

        count = 0
        for agent in self._agents.values():
            if team_name in agent.teams:
                if self.send_to_agent(agent.name, message, MessageType.BROADCAST):
                    count += 1

        print(f"{ANSI.CYAN}Broadcast to {team_name}: {count} agents{ANSI.RESET}")
        return count

    def focus_agent(self, agent_name: str) -> bool:
        """Focus on an agent's session in iTerm."""
        agent = self._agents.get(agent_name)
        if not agent:
            return False

        # This would call set_active_session and modify_sessions in real implementation
        print(f"{ANSI.GREEN}Focused on agent: {agent_name}{ANSI.RESET}")
        self._current_agent = agent_name
        return True

    def interrupt_agent(self, agent_name: str) -> bool:
        """Send interrupt signal (Ctrl+C) to an agent."""
        return self.send_to_agent(agent_name, "\x03", MessageType.SIGNAL, execute=False)

    # === UI Operations ===

    def _prev_agent(self) -> None:
        """Select previous agent."""
        agents = list(self._agents.keys())
        if not agents:
            return

        if self._current_agent in agents:
            idx = agents.index(self._current_agent)
            self._current_agent = agents[(idx - 1) % len(agents)]
        else:
            self._current_agent = agents[-1]

        print(f"Selected: {self._current_agent}")

    def _next_agent(self) -> None:
        """Select next agent."""
        agents = list(self._agents.keys())
        if not agents:
            return

        if self._current_agent in agents:
            idx = agents.index(self._current_agent)
            self._current_agent = agents[(idx + 1) % len(agents)]
        else:
            self._current_agent = agents[0]

        print(f"Selected: {self._current_agent}")

    def _focus_current_agent(self) -> None:
        """Focus on the currently selected agent."""
        if self._current_agent:
            self.focus_agent(self._current_agent)

    def _go_back(self) -> None:
        """Go back / deselect."""
        self._current_agent = None

    def _read_current_output(self) -> None:
        """Read output from current agent."""
        if self._current_agent:
            output = self.get_agent_output(self._current_agent)
            print(f"\n{ANSI.CYAN}=== Output from {self._current_agent} ==={ANSI.RESET}")
            print(output)
            print(f"{ANSI.CYAN}{'=' * 40}{ANSI.RESET}\n")

    def _send_command_prompt(self) -> None:
        """Prompt user to send a command to current agent."""
        if not self._current_agent:
            print("No agent selected. Use LB/RB to select an agent.")
            return

        # In a real implementation, this would show an input dialog
        print(f"Would prompt for command to send to {self._current_agent}")

    def _quick_message(self) -> None:
        """Show quick message options."""
        options = [
            MenuOption("Continue", "continue", "Tell agent to continue"),
            MenuOption("Stop", "stop", "Ask agent to stop"),
            MenuOption("Status?", "status", "Ask for status update"),
            MenuOption("Help", "help", "Ask for help"),
        ]

        result, choice = self._menu.select(
            "Quick Message:",
            options,
            title="Send to " + (self._current_agent or "agent"),
        )

        if result == MenuResult.SELECTED and self._current_agent:
            messages = {
                "continue": "Please continue with the current task.",
                "stop": "Please stop and wait for further instructions.",
                "status": "What is your current status?",
                "help": "I need help. Can you explain what you're doing?",
            }
            self.send_to_agent(self._current_agent, messages.get(choice, choice))

    def _team_broadcast(self) -> None:
        """Broadcast to a team."""
        if not self._teams:
            print("No teams available.")
            return

        # Select team
        options = [MenuOption(t.name, t.name, t.description) for t in self._teams.values()]
        result, team = self._menu.select("Select Team:", options, title="Team Broadcast")

        if result != MenuResult.SELECTED:
            return

        # Select message type
        messages = [
            MenuOption("Status check", "Check in with your status please."),
            MenuOption("Pause all", "Please pause your current work."),
            MenuOption("Resume all", "Please resume your work."),
            MenuOption("Custom...", "__custom__", "Type a custom message"),
        ]

        result, msg = self._menu.select("Broadcast Message:", messages)

        if result == MenuResult.SELECTED:
            if msg == "__custom__":
                print("Would prompt for custom message...")
            else:
                self.broadcast_to_team(team, msg)

    def _show_teams(self) -> None:
        """Show team selection menu."""
        if not self._teams:
            print("No teams available.")
            return

        options = []
        for team in self._teams.values():
            member_count = sum(1 for a in self._agents.values() if team.name in a.teams)
            options.append(MenuOption(
                f"{team.name} ({member_count})",
                team.name,
                team.description
            ))

        result, team = self._menu.select("Select Team:", options, title="Teams")

        if result == MenuResult.SELECTED:
            self._current_team = team
            self._show_team_agents(team)

    def _show_team_agents(self, team_name: str) -> None:
        """Show agents in a team."""
        agents = [a for a in self._agents.values() if team_name in a.teams]

        if not agents:
            print(f"No agents in team {team_name}")
            return

        options = [MenuOption(a.name, a.name, f"Session: {a.session_id[:8]}") for a in agents]
        result, agent = self._menu.select(f"Agents in {team_name}:", options)

        if result == MenuResult.SELECTED:
            self.select_agent(agent)
            self.focus_agent(agent)

    def _show_quick_actions(self) -> None:
        """Show quick actions menu."""
        options = [
            MenuOption("Refresh All", "refresh", "Refresh agent data"),
            MenuOption("Focus Agent", "focus", "Focus on selected agent"),
            MenuOption("Read Output", "read", "Read agent output"),
            MenuOption("Interrupt", "interrupt", "Send Ctrl+C to agent"),
            MenuOption("Notification Center", "notifications", "Open notifications"),
        ]

        result, action = self._menu.select("Quick Actions:", options, title="Actions")

        if result == MenuResult.SELECTED:
            if action == "refresh":
                self.refresh()
                print("Refreshed agent data.")
            elif action == "focus" and self._current_agent:
                self.focus_agent(self._current_agent)
            elif action == "read" and self._current_agent:
                self._read_current_output()
            elif action == "interrupt" and self._current_agent:
                self.interrupt_agent(self._current_agent)
            elif action == "notifications":
                self.notification_center.open()

    # === Display ===

    def show_status(self) -> None:
        """Print current status to console."""
        print(f"\n{ANSI.BOLD}=== Agent Hub Status ==={ANSI.RESET}")
        print(f"Agents: {len(self._agents)}")
        print(f"Teams: {len(self._teams)}")
        print(f"Current Agent: {self._current_agent or 'None'}")
        print(f"Unread Notifications: {self.notification_center.unread_count}")

        if self._current_agent:
            agent = self._agents.get(self._current_agent)
            if agent:
                print(f"\n{ANSI.CYAN}Current Agent Details:{ANSI.RESET}")
                print(f"  Name: {agent.name}")
                print(f"  Session: {agent.session_id}")
                print(f"  Teams: {', '.join(agent.teams) or 'None'}")

        print()


def create_agent_hub(gamepad: Optional[GamepadEmulator] = None) -> AgentHub:
    """Create and configure an agent hub."""
    hub = AgentHub(gamepad=gamepad)
    return hub


def demo():
    """Interactive demo of the agent hub."""
    import threading

    print("Agent Hub Demo")
    print("=" * 40)
    print()
    print("Controls:")
    print("  LB/RB (Q/E): Prev/Next agent")
    print("  A (Space): Focus agent")
    print("  Y (Y): Read output")
    print("  X (X): Send command")
    print("  START (Enter): Quick actions")
    print("  HOME (H): Notification center")
    print("  Ctrl+C: Quit")
    print()

    hub = create_agent_hub()

    # Keyboard to gamepad mapping
    def keyboard_listener():
        import tty
        import termios
        import select

        old_settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setraw(sys.stdin.fileno())

            while True:
                rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
                if rlist:
                    ch = sys.stdin.read(1)

                    if ch == '\x03':  # Ctrl+C
                        break
                    elif ch == 'q':
                        hub.gamepad.tap(GamepadButton.LB, 0.05)
                    elif ch == 'e':
                        hub.gamepad.tap(GamepadButton.RB, 0.05)
                    elif ch == ' ':
                        hub.gamepad.tap(GamepadButton.A, 0.05)
                    elif ch == 'y':
                        hub.gamepad.tap(GamepadButton.Y, 0.05)
                    elif ch == 'x':
                        hub.gamepad.tap(GamepadButton.X, 0.05)
                    elif ch == '\r':
                        hub.gamepad.tap(GamepadButton.START, 0.05)
                    elif ch == 'h':
                        hub.gamepad.tap(GamepadButton.HOME, 0.05)
                    elif ch == 's':
                        hub.show_status()
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

    # Start hub
    hub.start()

    # Start keyboard listener
    kb_thread = threading.Thread(target=keyboard_listener, daemon=True)
    kb_thread.start()

    print("Press 'S' to see status, 'Q/E' to cycle agents...")

    try:
        kb_thread.join()
    except KeyboardInterrupt:
        # Allow Ctrl+C to break out of the demo loop and proceed to graceful shutdown.
        pass

    hub.stop()
    print(ANSI.SHOW_CURSOR)
    print("\nDemo ended.")


if __name__ == '__main__':
    demo()
