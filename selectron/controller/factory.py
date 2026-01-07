"""
Factory functions for creating controller components.

Provides dependency injection and makes it easy to swap implementations
(e.g., use MockAgentClient for testing without iTerm).
"""

from typing import Optional

from .interfaces import AgentClient, MockAgentClient
from .core.emulator import GamepadEmulator
from .core.notification_center import NotificationCenter, create_notification_center
from .core.agent_hub import AgentHub, create_agent_hub
from .core.choice_engine import ChoiceEngine, AnswerGenerator, create_choice_engine


def create_mock_client() -> AgentClient:
    """
    Create a mock agent client for testing without iTerm.

    Returns:
        MockAgentClient instance that implements AgentClient protocol
    """
    return MockAgentClient()


def create_iterm_client(cache_ttl: float = 5.0) -> AgentClient:
    """
    Create an iTerm agent client for real iTerm integration.

    Args:
        cache_ttl: Cache time-to-live in seconds (default 5.0)

    Returns:
        ITermAgentClient instance that implements AgentClient protocol
    """
    from .bridges.iterm.client import ITermAgentClient
    return ITermAgentClient(cache_ttl=cache_ttl)


def create_notification_center_with_client(
    gamepad: Optional[GamepadEmulator] = None,
    client: Optional[AgentClient] = None,
) -> NotificationCenter:
    """
    Create a NotificationCenter with optional client injection.

    Args:
        gamepad: GamepadEmulator instance (creates one if not provided)
        client: AgentClient instance for fetching notifications

    Returns:
        Configured NotificationCenter
    """
    center = create_notification_center(gamepad)
    # NotificationCenter currently uses mock data, but client could be used
    # to fetch real notifications in the future
    return center


def create_agent_hub_with_client(
    gamepad: Optional[GamepadEmulator] = None,
    client: Optional[AgentClient] = None,
    auto_refresh: bool = True,
    refresh_interval: float = 5.0,
) -> AgentHub:
    """
    Create an AgentHub with optional client injection.

    Args:
        gamepad: GamepadEmulator instance (creates one if not provided)
        client: AgentClient instance for fetching agents/teams
        auto_refresh: Enable auto-refresh of agent data
        refresh_interval: Refresh interval in seconds

    Returns:
        Configured AgentHub
    """
    hub = AgentHub(
        gamepad=gamepad,
        auto_refresh=auto_refresh,
        refresh_interval=refresh_interval,
    )
    # Store client for future use when AgentHub is updated to use it
    hub._client = client
    return hub


def create_choice_engine_with_generator(
    generator: Optional[AnswerGenerator] = None,
    gamepad: Optional[GamepadEmulator] = None,
) -> ChoiceEngine:
    """
    Create a ChoiceEngine with optional custom generator.

    Args:
        generator: AnswerGenerator instance (uses MockAnswerGenerator if not provided)
        gamepad: GamepadEmulator instance

    Returns:
        Configured ChoiceEngine
    """
    return create_choice_engine(generator=generator, gamepad=gamepad)


def create_iterm_controller(session_id: Optional[str] = None):
    """
    Create a GamepadTerminalController for iTerm.

    Args:
        session_id: iTerm session ID to control

    Returns:
        GamepadTerminalController instance
    """
    from .bridges.iterm.bridge import GamepadTerminalController
    if session_id:
        return GamepadTerminalController(session_id)
    else:
        # Return ITermBridge without a session for configuration
        from .bridges.iterm.bridge import ITermBridge
        return ITermBridge()


def create_team_window_manager(client: Optional[AgentClient] = None):
    """
    Create a TeamWindowManager with optional client injection.

    Args:
        client: AgentClient instance (with async capabilities)

    Returns:
        TeamWindowManager instance
    """
    from .bridges.iterm.window_manager import TeamWindowManager
    return TeamWindowManager(mcp_client=client)


# Convenience function to get a complete setup for testing
def create_test_setup():
    """
    Create a complete test setup with mock components.

    Returns:
        Dictionary with gamepad, client, hub, notification_center, choice_engine
    """
    gamepad = GamepadEmulator("Test Controller")
    client = create_mock_client()

    return {
        "gamepad": gamepad,
        "client": client,
        "hub": create_agent_hub_with_client(gamepad=gamepad, client=client),
        "notification_center": create_notification_center(gamepad=gamepad),
        "choice_engine": create_choice_engine(gamepad=gamepad),
    }


# Convenience function to get a complete setup for production
def create_iterm_setup():
    """
    Create a complete production setup with iTerm components.

    Returns:
        Dictionary with gamepad, client, hub, notification_center, choice_engine
    """
    gamepad = GamepadEmulator("iTerm Controller")
    client = create_iterm_client()

    return {
        "gamepad": gamepad,
        "client": client,
        "hub": create_agent_hub_with_client(gamepad=gamepad, client=client),
        "notification_center": create_notification_center(gamepad=gamepad),
        "choice_engine": create_choice_engine(gamepad=gamepad),
        "window_manager": create_team_window_manager(client=client),
    }
