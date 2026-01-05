#!/usr/bin/env python3
"""
Notification Center for Gamepad Controller.

A macOS-style notification center that can be triggered with a gamepad button.
Shows agent notifications, allows team/agent navigation, and session switching.
"""

import sys
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, List, Optional, Any
from threading import Event, Thread, Lock
from datetime import datetime

from .emulator import GamepadEmulator, GamepadButton, DPadDirection
from .menu import ANSI


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
        icons = {
            NotificationLevel.INFO: "ℹ️",
            NotificationLevel.SUCCESS: "✅",
            NotificationLevel.WARNING: "⚠️",
            NotificationLevel.ERROR: "❌",
            NotificationLevel.BLOCKED: "🚫",
        }
        return icons.get(self.level, "📌")

    @property
    def color(self) -> str:
        colors = {
            NotificationLevel.INFO: ANSI.BLUE,
            NotificationLevel.SUCCESS: ANSI.GREEN,
            NotificationLevel.WARNING: ANSI.YELLOW,
            NotificationLevel.ERROR: ANSI.RED,
            NotificationLevel.BLOCKED: ANSI.MAGENTA,
        }
        return colors.get(self.level, ANSI.WHITE)


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


class NotificationCenterState(Enum):
    """States of the notification center."""
    CLOSED = auto()
    NOTIFICATIONS = auto()
    TEAMS = auto()
    AGENTS = auto()
    AGENT_DETAIL = auto()


class NotificationCenter:
    """
    macOS-style notification center for gamepad.

    Features:
    - Trigger with Home/Guide button to open
    - Navigate with D-pad
    - Switch views with bumpers (LB/RB)
    - Select with A, close with B
    - Shows notifications, teams, agents

    Button Mapping:
    - HOME/GUIDE: Toggle notification center
    - LB/RB: Switch between views (Notifications/Teams/Agents)
    - D-pad: Navigate within current view
    - A: Select/Action
    - B: Back/Close
    - Y: Mark as read / Quick action
    - X: Refresh
    """

    VIEWS = ["Notifications", "Teams", "Agents"]

    def __init__(
        self,
        gamepad: GamepadEmulator,
        mcp_client: Optional[Any] = None,
    ):
        self.gamepad = gamepad
        self.mcp_client = mcp_client

        # State
        self._state = NotificationCenterState.CLOSED
        self._current_view = 0  # Index into VIEWS
        self._current_index = 0
        self._selected_team: Optional[str] = None
        self._selected_agent: Optional[Agent] = None

        # Data
        self._notifications: List[Notification] = []
        self._teams: List[Team] = []
        self._agents: List[Agent] = []

        # UI state
        self._visible = False
        self._needs_render = True
        self._render_lock = Lock()

        # Callbacks for external integration
        self._on_agent_select: Optional[Callable[[Agent], None]] = None
        self._on_team_select: Optional[Callable[[Team], None]] = None
        self._on_notification_action: Optional[Callable[[Notification], None]] = None

        # Original callbacks storage
        self._original_callbacks = {}

        # Background refresh
        self._refresh_interval = 5.0  # seconds
        self._refresh_thread: Optional[Thread] = None
        self._stop_refresh = Event()

    @property
    def is_open(self) -> bool:
        return self._visible

    @property
    def unread_count(self) -> int:
        return sum(1 for n in self._notifications if not n.read)

    def set_mcp_client(self, client: Any) -> None:
        """Set the MCP client for fetching data."""
        self.mcp_client = client

    def on_agent_select(self, callback: Callable[[Agent], None]) -> None:
        """Set callback for when an agent is selected."""
        self._on_agent_select = callback

    def on_team_select(self, callback: Callable[[Team], None]) -> None:
        """Set callback for when a team is selected."""
        self._on_team_select = callback

    def on_notification_action(self, callback: Callable[[Notification], None]) -> None:
        """Set callback for notification actions."""
        self._on_notification_action = callback

    def bind_trigger(self, button: GamepadButton = GamepadButton.HOME) -> None:
        """Bind a button to toggle the notification center."""
        def on_trigger(btn: GamepadButton, pressed: bool):
            if btn == button and pressed:
                self.toggle()

        self.gamepad.on_button(on_trigger)

    def toggle(self) -> None:
        """Toggle the notification center open/closed."""
        if self._visible:
            self.close()
        else:
            self.open()

    def open(self) -> None:
        """Open the notification center."""
        if self._visible:
            return

        self._visible = True
        self._state = NotificationCenterState.NOTIFICATIONS
        self._current_view = 0
        self._current_index = 0
        self._needs_render = True

        # Save and replace callbacks
        self._save_callbacks()
        self._setup_navigation_callbacks()

        # Start refresh thread
        self._start_refresh()

        # Initial data fetch
        self.refresh_data()

        # Render
        self._render()

    def close(self) -> None:
        """Close the notification center."""
        if not self._visible:
            return

        self._visible = False
        self._state = NotificationCenterState.CLOSED

        # Stop refresh
        self._stop_refresh.set()

        # Restore callbacks
        self._restore_callbacks()

        # Clear display
        self._clear_display()

    def refresh_data(self) -> None:
        """Refresh data from MCP (or use mock data)."""
        # For now, use mock data. In real use, this would call MCP.
        self._refresh_notifications()
        self._refresh_teams()
        self._refresh_agents()
        self._needs_render = True

    def _refresh_notifications(self) -> None:
        """Fetch notifications from MCP or use mock."""
        # Mock notifications for demo
        if not self._notifications:
            self._notifications = [
                Notification(
                    id="1",
                    agent="morpholint-lead",
                    level=NotificationLevel.SUCCESS,
                    summary="Build completed successfully",
                    context="All 42 tests passed",
                    action_hint="View build output",
                ),
                Notification(
                    id="2",
                    agent="github-researcher",
                    level=NotificationLevel.INFO,
                    summary="Found 3 relevant repositories",
                    context="Searching for orchestration patterns",
                ),
                Notification(
                    id="3",
                    agent="alpha",
                    level=NotificationLevel.WARNING,
                    summary="Rate limit approaching",
                    context="API calls: 450/500",
                    action_hint="Consider throttling",
                ),
                Notification(
                    id="4",
                    agent="beta",
                    level=NotificationLevel.BLOCKED,
                    summary="Waiting for user input",
                    context="Need confirmation to proceed",
                    action_hint="Press A to respond",
                ),
            ]

    def _refresh_teams(self) -> None:
        """Fetch teams from MCP or use mock."""
        if not self._teams:
            self._teams = [
                Team("orchestration-research", "Multi-agent orchestration research"),
                Team("morpholint", "MorphoLint linting project"),
                Team("docs-testing", "Documentation testing"),
                Team("duality-validation", "Duality theory validation"),
                Team("preposition-research", "Preposition analysis"),
            ]

    def _refresh_agents(self) -> None:
        """Fetch agents from MCP or use mock."""
        if not self._agents:
            self._agents = [
                Agent("morpholint-lead", "55FBCC14", ["morpholint"]),
                Agent("alpha", "84A3FDE0", []),
                Agent("beta", "7E700876", []),
                Agent("gamma", "F365CFB8", []),
                Agent("github-researcher", "91B4B9F3", ["orchestration-research"]),
                Agent("pypi-researcher", "94E72346", ["orchestration-research"]),
                Agent("gamepad-demo", "BCBC6F42", []),
            ]

    def _start_refresh(self) -> None:
        """Start background refresh thread."""
        self._stop_refresh.clear()

        def refresh_loop():
            while not self._stop_refresh.wait(self._refresh_interval):
                self.refresh_data()
                if self._visible:
                    self._render()

        self._refresh_thread = Thread(target=refresh_loop, daemon=True)
        self._refresh_thread.start()

    def _save_callbacks(self) -> None:
        """Save current gamepad callbacks."""
        self._original_callbacks = {
            'button': self.gamepad._button_callbacks.copy(),
            'dpad': self.gamepad._dpad_callbacks.copy(),
        }

    def _restore_callbacks(self) -> None:
        """Restore original gamepad callbacks."""
        if self._original_callbacks:
            self.gamepad._button_callbacks = self._original_callbacks.get('button', [])
            self.gamepad._dpad_callbacks = self._original_callbacks.get('dpad', [])

    def _setup_navigation_callbacks(self) -> None:
        """Set up navigation callbacks for the notification center."""
        self.gamepad._button_callbacks.clear()
        self.gamepad._dpad_callbacks.clear()

        def on_button(button: GamepadButton, pressed: bool):
            if not pressed:
                return

            if button == GamepadButton.HOME:
                self.close()
            elif button == GamepadButton.B:
                self._handle_back()
            elif button == GamepadButton.A:
                self._handle_select()
            elif button == GamepadButton.LB:
                self._switch_view(-1)
            elif button == GamepadButton.RB:
                self._switch_view(1)
            elif button == GamepadButton.Y:
                self._handle_quick_action()
            elif button == GamepadButton.X:
                self.refresh_data()
                self._render()

        def on_dpad(direction: DPadDirection):
            if direction == DPadDirection.UP:
                self._navigate(-1)
            elif direction == DPadDirection.DOWN:
                self._navigate(1)
            elif direction in (DPadDirection.LEFT, DPadDirection.RIGHT):
                # Could be used for sub-navigation
                pass

        self.gamepad.on_button(on_button)
        self.gamepad.on_dpad(on_dpad)

    def _switch_view(self, delta: int) -> None:
        """Switch between views."""
        self._current_view = (self._current_view + delta) % len(self.VIEWS)
        self._current_index = 0

        if self._current_view == 0:
            self._state = NotificationCenterState.NOTIFICATIONS
        elif self._current_view == 1:
            self._state = NotificationCenterState.TEAMS
        elif self._current_view == 2:
            self._state = NotificationCenterState.AGENTS

        self._render()

    def _navigate(self, delta: int) -> None:
        """Navigate within current view."""
        max_index = self._get_current_list_length() - 1
        if max_index < 0:
            return

        self._current_index = max(0, min(max_index, self._current_index + delta))
        self._render()

    def _get_current_list_length(self) -> int:
        """Get length of current view's list."""
        if self._state == NotificationCenterState.NOTIFICATIONS:
            return len(self._notifications)
        elif self._state == NotificationCenterState.TEAMS:
            return len(self._teams)
        elif self._state == NotificationCenterState.AGENTS:
            return len(self._agents)
        return 0

    def _handle_select(self) -> None:
        """Handle A button - select current item."""
        if self._state == NotificationCenterState.NOTIFICATIONS:
            if self._notifications and self._current_index < len(self._notifications):
                notif = self._notifications[self._current_index]
                notif.read = True
                if self._on_notification_action:
                    self._on_notification_action(notif)
                self._render()

        elif self._state == NotificationCenterState.TEAMS:
            if self._teams and self._current_index < len(self._teams):
                team = self._teams[self._current_index]
                self._selected_team = team.name
                if self._on_team_select:
                    self._on_team_select(team)
                # Switch to agents view filtered by team
                self._current_view = 2
                self._state = NotificationCenterState.AGENTS
                self._current_index = 0
                self._render()

        elif self._state == NotificationCenterState.AGENTS:
            if self._agents and self._current_index < len(self._agents):
                agent = self._agents[self._current_index]
                self._selected_agent = agent
                if self._on_agent_select:
                    self._on_agent_select(agent)
                # Could switch focus to agent's session
                self.close()

    def _handle_back(self) -> None:
        """Handle B button - go back or close."""
        if self._state == NotificationCenterState.AGENT_DETAIL:
            self._state = NotificationCenterState.AGENTS
            self._render()
        elif self._selected_team:
            self._selected_team = None
            self._current_view = 1
            self._state = NotificationCenterState.TEAMS
            self._render()
        else:
            self.close()

    def _handle_quick_action(self) -> None:
        """Handle Y button - quick action (mark read, etc)."""
        if self._state == NotificationCenterState.NOTIFICATIONS:
            if self._notifications and self._current_index < len(self._notifications):
                self._notifications[self._current_index].read = True
                self._render()

    def _clear_display(self) -> None:
        """Clear the notification center display."""
        # Move cursor up and clear lines
        print(ANSI.SHOW_CURSOR)
        # Just print some newlines to push it off
        print("\n" * 2)

    def _render(self) -> None:
        """Render the notification center."""
        if not self._visible:
            return

        with self._render_lock:
            lines = self._build_display()

            # Clear screen area and print
            sys.stdout.write('\033[2J\033[H')  # Clear screen, move to top
            print(ANSI.HIDE_CURSOR)

            for line in lines:
                print(line)

            sys.stdout.flush()

    def _build_display(self) -> List[str]:
        """Build the display lines."""
        lines = []
        width = 60

        # Header
        lines.append(f"{ANSI.BG_BLUE}{ANSI.WHITE}{ANSI.BOLD}")
        lines.append(f"{'═' * width}")

        # Tab bar
        tabs = []
        for i, view in enumerate(self.VIEWS):
            if i == self._current_view:
                tabs.append(f"{ANSI.UNDERLINE}[{view}]{ANSI.RESET}{ANSI.BG_BLUE}{ANSI.WHITE}")
            else:
                tabs.append(f" {view} ")

        tab_line = "  ".join(tabs)
        unread_badge = f" ({self.unread_count})" if self.unread_count > 0 else ""
        lines.append(f"  🎮 Notification Center{unread_badge}  │  {tab_line}")
        lines.append(f"{'─' * width}{ANSI.RESET}")

        # Content based on current view
        if self._state == NotificationCenterState.NOTIFICATIONS:
            lines.extend(self._render_notifications(width))
        elif self._state == NotificationCenterState.TEAMS:
            lines.extend(self._render_teams(width))
        elif self._state == NotificationCenterState.AGENTS:
            lines.extend(self._render_agents(width))

        # Footer
        lines.append("")
        lines.append(f"{ANSI.DIM}{'─' * width}")
        lines.append(f"[A] Select  [B] Back  [LB/RB] Switch View  [X] Refresh  [HOME] Close{ANSI.RESET}")

        return lines

    def _render_notifications(self, width: int) -> List[str]:
        """Render notifications list."""
        lines = []

        if not self._notifications:
            lines.append("")
            lines.append(f"  {ANSI.DIM}No notifications{ANSI.RESET}")
            lines.append("")
            return lines

        for i, notif in enumerate(self._notifications[:10]):  # Show max 10
            is_selected = i == self._current_index
            prefix = "▶ " if is_selected else "  "
            read_marker = "" if notif.read else "●"

            # Build notification line
            color = notif.color if is_selected else ANSI.RESET
            bg = ANSI.BG_WHITE + ANSI.BLACK if is_selected else ""

            line = f"{bg}{color}{prefix}{notif.icon} {read_marker} [{notif.agent}] {notif.summary[:40]}{ANSI.RESET}"
            lines.append(line)

            # Show context if selected
            if is_selected and notif.context:
                lines.append(f"     {ANSI.DIM}{notif.context}{ANSI.RESET}")
            if is_selected and notif.action_hint:
                lines.append(f"     {ANSI.CYAN}💡 {notif.action_hint}{ANSI.RESET}")

        return lines

    def _render_teams(self, width: int) -> List[str]:
        """Render teams list."""
        lines = []

        if not self._teams:
            lines.append("")
            lines.append(f"  {ANSI.DIM}No teams{ANSI.RESET}")
            lines.append("")
            return lines

        for i, team in enumerate(self._teams):
            is_selected = i == self._current_index
            prefix = "▶ " if is_selected else "  "
            color = ANSI.GREEN if is_selected else ANSI.RESET

            member_count = len([a for a in self._agents if team.name in a.teams])
            line = f"{color}{prefix}👥 {team.name} ({member_count} agents){ANSI.RESET}"
            lines.append(line)

            if is_selected and team.description:
                lines.append(f"     {ANSI.DIM}{team.description}{ANSI.RESET}")

        return lines

    def _render_agents(self, width: int) -> List[str]:
        """Render agents list."""
        lines = []

        # Filter by selected team if any
        agents = self._agents
        if self._selected_team:
            agents = [a for a in agents if self._selected_team in a.teams]
            lines.append(f"  {ANSI.CYAN}Team: {self._selected_team}{ANSI.RESET}")
            lines.append("")

        if not agents:
            lines.append("")
            lines.append(f"  {ANSI.DIM}No agents{ANSI.RESET}")
            lines.append("")
            return lines

        for i, agent in enumerate(agents):
            is_selected = i == self._current_index
            prefix = "▶ " if is_selected else "  "
            color = ANSI.GREEN if is_selected else ANSI.RESET

            # Status indicator
            if agent.locked:
                status = "🔒"
            elif agent.is_processing:
                status = "⏳"
            else:
                status = "🤖"

            teams_str = ", ".join(agent.teams) if agent.teams else "no team"
            line = f"{color}{prefix}{status} {agent.name}{ANSI.RESET}"
            lines.append(line)

            if is_selected:
                lines.append(f"     {ANSI.DIM}Teams: {teams_str}{ANSI.RESET}")
                lines.append(f"     {ANSI.DIM}Session: {agent.session_id[:8]}...{ANSI.RESET}")

        return lines


def create_notification_center(gamepad: GamepadEmulator) -> NotificationCenter:
    """Create a notification center with standard bindings."""
    nc = NotificationCenter(gamepad)
    nc.bind_trigger(GamepadButton.HOME)
    return nc


def demo():
    """Interactive demo of the notification center."""
    import threading

    print("Notification Center Demo")
    print("=" * 40)
    print()
    print("Controls:")
    print("  H: Toggle notification center (HOME button)")
    print("  Arrow Up/Down: Navigate")
    print("  Q/E: Switch views (LB/RB)")
    print("  Space: Select (A)")
    print("  Escape: Back/Close (B)")
    print("  R: Refresh (X)")
    print("  Ctrl+C: Quit")
    print()

    gamepad = GamepadEmulator("NC Demo")
    nc = create_notification_center(gamepad)

    # Set up callbacks
    def on_agent_select(agent):
        print(f"\n>>> Selected agent: {agent.name}")

    def on_notification_action(notif):
        print(f"\n>>> Action on notification from {notif.agent}: {notif.summary}")

    nc.on_agent_select(on_agent_select)
    nc.on_notification_action(on_notification_action)

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
                    elif ch == 'h':
                        gamepad.tap(GamepadButton.HOME, 0.05)
                    elif ch == '\x1b':
                        rlist2, _, _ = select.select([sys.stdin], [], [], 0.05)
                        if rlist2:
                            ch += sys.stdin.read(2)
                            if ch == '\x1b[A':
                                gamepad.set_dpad(DPadDirection.UP)
                                time.sleep(0.05)
                                gamepad.set_dpad(DPadDirection.NONE)
                            elif ch == '\x1b[B':
                                gamepad.set_dpad(DPadDirection.DOWN)
                                time.sleep(0.05)
                                gamepad.set_dpad(DPadDirection.NONE)
                        else:
                            gamepad.tap(GamepadButton.B, 0.05)
                    elif ch == ' ':
                        gamepad.tap(GamepadButton.A, 0.05)
                    elif ch == 'q':
                        gamepad.tap(GamepadButton.LB, 0.05)
                    elif ch == 'e':
                        gamepad.tap(GamepadButton.RB, 0.05)
                    elif ch == 'r':
                        gamepad.tap(GamepadButton.X, 0.05)
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

    kb_thread = threading.Thread(target=keyboard_listener, daemon=True)
    kb_thread.start()

    print("Press 'H' to open the notification center...")

    try:
        kb_thread.join()
    except KeyboardInterrupt:
        # Allow Ctrl+C to stop the demo without showing a traceback.
        pass

    print(ANSI.SHOW_CURSOR)
    print("\nDemo ended.")


if __name__ == '__main__':
    demo()
