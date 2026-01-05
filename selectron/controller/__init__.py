"""
Game controller emulation and mapping for Selectron.

This module provides a software-driven game controller emulator
that can be mapped to terminal/IDE actions.

Architecture:
    - types.py: Shared data types (Agent, Team, Notification, MCPResponse)
    - interfaces.py: Protocols (AgentClient) and MockAgentClient
    - core/: Platform-agnostic components (emulator, mapper, menu, etc.)
    - bridges/: Platform-specific adapters (iterm/, vscode/ future)
    - factory.py: Factory functions for dependency injection
"""

# === Types (shared data types) ===
from .types import (
    Agent,
    Team,
    Notification,
    NotificationLevel,
    MCPResponse,
)

# === Interfaces (protocols and mocks) ===
from .interfaces import (
    AgentClient,
    AgentClientAsync,
    MockAgentClient,
)

# === Core Components ===
from .core.emulator import (
    GamepadEmulator,
    GamepadState,
    GamepadButton,
    DPadDirection,
    StickState,
    TriggerState,
)
from .core.mapper import (
    ControllerMapper,
    ActionBinding,
    ActionType,
    ControllerProfile,
    Keys,
    create_terminal_navigation_profile,
    create_vim_profile,
)
from .core.executors import (
    ActionExecutor,
    PrintExecutor,
    CallbackExecutor,
)
from .core.menu import (
    GamepadMenu,
    MenuOption,
    MenuConfig,
    MenuResult,
    ANSI,
)
from .core.notification_center import (
    NotificationCenter,
    NotificationCenterState,
    create_notification_center,
)
from .core.agent_hub import (
    AgentHub,
    AgentStatus,
    AgentMessage,
    MessageType,
    create_agent_hub,
)
from .core.choice_engine import (
    ChoiceEngine,
    ChoiceSet,
    AnswerChoice,
    ChoiceStatus,
    AnswerGenerator,
    MockAnswerGenerator,
    ChoicePanel,
    InlineListItem,
    InlineListSelector,
    create_choice_engine,
)

# === iTerm Bridge (platform-specific) ===
from .bridges.iterm.client import (
    ITermAgentClient,
    get_iterm_client,
    reset_iterm_client,
    # Backward compatibility aliases
    ITermMCPClient,
    get_mcp_client,
    reset_mcp_client,
)
from .bridges.iterm.executor import (
    AppleScriptExecutor,
    ITermExecutor,
)
from .bridges.iterm.window_manager import (
    TeamWindowManager,
    TeamWindow,
    AgentSession,
    WindowLayout,
    ROLE_COLORS,
    HIGHLIGHT_COLOR,
    create_team_window_manager,
)
from .bridges.iterm.bridge import (
    ITermBridge,
    ITermSession,
    GamepadTerminalController,
    create_demo_profile,
)

# === Factory Functions ===
from .factory import (
    create_mock_client,
    create_iterm_client,
    create_notification_center_with_client,
    create_agent_hub_with_client,
    create_choice_engine_with_generator,
    create_iterm_controller,
    create_test_setup,
    create_iterm_setup,
)

__all__ = [
    # Types
    "Agent",
    "Team",
    "Notification",
    "NotificationLevel",
    "MCPResponse",
    # Interfaces
    "AgentClient",
    "AgentClientAsync",
    "MockAgentClient",
    # Emulator
    "GamepadEmulator",
    "GamepadState",
    "GamepadButton",
    "DPadDirection",
    "StickState",
    "TriggerState",
    # Mapper
    "ControllerMapper",
    "ActionBinding",
    "ActionType",
    "ControllerProfile",
    "Keys",
    "create_terminal_navigation_profile",
    "create_vim_profile",
    # Executors
    "ActionExecutor",
    "PrintExecutor",
    "CallbackExecutor",
    "AppleScriptExecutor",
    "ITermExecutor",
    # Menu
    "GamepadMenu",
    "MenuOption",
    "MenuConfig",
    "MenuResult",
    "ANSI",
    # Notification Center
    "NotificationCenter",
    "NotificationCenterState",
    "create_notification_center",
    # Agent Hub
    "AgentHub",
    "AgentStatus",
    "AgentMessage",
    "MessageType",
    "create_agent_hub",
    # Choice Engine
    "ChoiceEngine",
    "ChoiceSet",
    "AnswerChoice",
    "ChoiceStatus",
    "AnswerGenerator",
    "MockAnswerGenerator",
    "ChoicePanel",
    "InlineListItem",
    "InlineListSelector",
    "create_choice_engine",
    # iTerm Client
    "ITermAgentClient",
    "get_iterm_client",
    "reset_iterm_client",
    # Backward compat aliases
    "ITermMCPClient",
    "get_mcp_client",
    "reset_mcp_client",
    # iTerm Bridge
    "ITermBridge",
    "ITermSession",
    "GamepadTerminalController",
    "create_demo_profile",
    # Team Windows
    "TeamWindowManager",
    "TeamWindow",
    "AgentSession",
    "WindowLayout",
    "ROLE_COLORS",
    "HIGHLIGHT_COLOR",
    "create_team_window_manager",
    # Factory Functions
    "create_mock_client",
    "create_iterm_client",
    "create_notification_center_with_client",
    "create_agent_hub_with_client",
    "create_choice_engine_with_generator",
    "create_iterm_controller",
    "create_test_setup",
    "create_iterm_setup",
]
