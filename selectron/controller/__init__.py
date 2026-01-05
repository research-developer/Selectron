"""
Game controller emulation and mapping for Selectron.

This module provides a software-driven game controller emulator
that can be mapped to terminal/IDE actions.
"""

from .emulator import GamepadEmulator, GamepadState, GamepadButton, DPadDirection
from .mapper import (
    ControllerMapper,
    ActionBinding,
    ActionType,
    ControllerProfile,
    Keys,
    create_terminal_navigation_profile,
    create_vim_profile,
)
from .executors import (
    ActionExecutor,
    PrintExecutor,
    AppleScriptExecutor,
    ITermExecutor,
    CallbackExecutor,
)
from .menu import (
    GamepadMenu,
    MenuOption,
    MenuConfig,
    MenuResult,
)
from .iterm_bridge import (
    ITermBridge,
    GamepadTerminalController,
)
from .notification_center import (
    NotificationCenter,
    Notification,
    NotificationLevel,
    Agent,
    Team,
    create_notification_center,
)
from .agent_hub import (
    AgentHub,
    AgentStatus,
    AgentMessage,
    MessageType,
    create_agent_hub,
)
from .team_windows import (
    TeamWindowManager,
    TeamWindow,
    AgentSession,
    WindowLayout,
    create_team_window_manager,
)
from .mcp_client import (
    ITermMCPClient,
    MCPResponse,
    get_mcp_client,
    reset_mcp_client,
)

__all__ = [
    # Emulator
    'GamepadEmulator',
    'GamepadState',
    'GamepadButton',
    'DPadDirection',
    # Mapper
    'ControllerMapper',
    'ActionBinding',
    'ActionType',
    'ControllerProfile',
    'Keys',
    'create_terminal_navigation_profile',
    'create_vim_profile',
    # Executors
    'ActionExecutor',
    'PrintExecutor',
    'AppleScriptExecutor',
    'ITermExecutor',
    'CallbackExecutor',
    # Menu
    'GamepadMenu',
    'MenuOption',
    'MenuConfig',
    'MenuResult',
    # iTerm Bridge
    'ITermBridge',
    'GamepadTerminalController',
    # Notification Center
    'NotificationCenter',
    'Notification',
    'NotificationLevel',
    'Agent',
    'Team',
    'create_notification_center',
    # Agent Hub
    'AgentHub',
    'AgentStatus',
    'AgentMessage',
    'MessageType',
    'create_agent_hub',
    # Team Windows
    'TeamWindowManager',
    'TeamWindow',
    'AgentSession',
    'WindowLayout',
    'create_team_window_manager',
    # MCP Client
    'ITermMCPClient',
    'MCPResponse',
    'get_mcp_client',
    'reset_mcp_client',
]
