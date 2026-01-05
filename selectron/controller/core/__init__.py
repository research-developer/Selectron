"""
Core controller components - pure Python with no external dependencies.

These modules form the domain logic layer and should not import from bridges/.
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
    CallbackExecutor,
)
from .menu import (
    GamepadMenu,
    MenuOption,
    MenuConfig,
    MenuResult,
    ANSI,
)
from .notification_center import (
    NotificationCenter,
    NotificationCenterState,
    create_notification_center,
)
from .agent_hub import (
    AgentHub,
    AgentStatus,
    AgentMessage,
    MessageType,
    create_agent_hub,
)
from .choice_engine import (
    ChoiceEngine,
    ChoiceSet,
    AnswerChoice,
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
    'CallbackExecutor',
    # Menu
    'GamepadMenu',
    'MenuOption',
    'MenuConfig',
    'MenuResult',
    'ANSI',
    # Notification Center
    'NotificationCenter',
    'NotificationCenterState',
    'create_notification_center',
    # Agent Hub
    'AgentHub',
    'AgentStatus',
    'AgentMessage',
    'MessageType',
    'create_agent_hub',
    # Choice Engine
    'ChoiceEngine',
    'ChoiceSet',
    'AnswerChoice',
]
