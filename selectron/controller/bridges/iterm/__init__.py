"""
iTerm bridge adapters for Selectron.

Provides iTerm-specific implementations of the controller interfaces.
"""

from .client import ITermAgentClient, get_iterm_client, reset_iterm_client
from .executor import AppleScriptExecutor, ITermExecutor
from .window_manager import (
    TeamWindowManager,
    TeamWindow,
    AgentSession,
    WindowLayout,
    ROLE_COLORS,
    HIGHLIGHT_COLOR,
    create_team_window_manager,
)
from .bridge import (
    ITermBridge,
    ITermSession,
    GamepadTerminalController,
    create_demo_profile,
)

__all__ = [
    # Client
    "ITermAgentClient",
    "get_iterm_client",
    "reset_iterm_client",
    # Executors
    "AppleScriptExecutor",
    "ITermExecutor",
    # Window Manager
    "TeamWindowManager",
    "TeamWindow",
    "AgentSession",
    "WindowLayout",
    "ROLE_COLORS",
    "HIGHLIGHT_COLOR",
    "create_team_window_manager",
    # Bridge
    "ITermBridge",
    "ITermSession",
    "GamepadTerminalController",
    "create_demo_profile",
]
