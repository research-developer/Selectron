"""
Core action executors - abstract base and generic implementations.

Platform-specific executors are in bridges/.
"""

from abc import ABC, abstractmethod
from typing import Callable, Optional

from .mapper import ActionBinding, ActionType


class ActionExecutor(ABC):
    """Base class for action executors."""

    @abstractmethod
    def execute(self, binding: ActionBinding) -> None:
        """Execute an action binding."""
        pass

    @abstractmethod
    def send_key(self, key: str) -> None:
        """Send a single key press."""
        pass

    @abstractmethod
    def send_key_combo(self, *keys: str) -> None:
        """Send a key combination (e.g., Ctrl+C)."""
        pass

    @abstractmethod
    def send_text(self, text: str) -> None:
        """Type a text string."""
        pass


class PrintExecutor(ActionExecutor):
    """
    Simple executor that just prints actions.
    Useful for testing/debugging.
    """

    def __init__(self, prefix: str = ""):
        self.prefix = prefix

    def execute(self, binding: ActionBinding) -> None:
        print(f"{self.prefix}Execute: {binding.action_type.name} -> {binding.value}")

        if binding.action_type == ActionType.KEY:
            self.send_key(binding.value)
        elif binding.action_type == ActionType.KEY_COMBO:
            self.send_key_combo(*binding.value)
        elif binding.action_type == ActionType.TEXT:
            self.send_text(binding.value)
        elif binding.action_type == ActionType.COMMAND:
            print(f"{self.prefix}Command: {binding.value}")
        elif binding.action_type == ActionType.CALLBACK:
            if callable(binding.value):
                binding.value()

    def send_key(self, key: str) -> None:
        print(f"{self.prefix}Key: {key}")

    def send_key_combo(self, *keys: str) -> None:
        print(f"{self.prefix}Combo: {'+'.join(keys)}")

    def send_text(self, text: str) -> None:
        print(f"{self.prefix}Text: {text}")


class CallbackExecutor(ActionExecutor):
    """
    Executor that routes all actions to a callback function.
    Useful for integration with custom systems.
    """

    def __init__(
        self,
        on_key: Optional[Callable[[str], None]] = None,
        on_combo: Optional[Callable[[tuple], None]] = None,
        on_text: Optional[Callable[[str], None]] = None,
        on_command: Optional[Callable[[str], None]] = None,
    ):
        self._on_key = on_key
        self._on_combo = on_combo
        self._on_text = on_text
        self._on_command = on_command

    def execute(self, binding: ActionBinding) -> None:
        if binding.action_type == ActionType.KEY:
            self.send_key(binding.value)
        elif binding.action_type == ActionType.KEY_COMBO:
            self.send_key_combo(*binding.value)
        elif binding.action_type == ActionType.TEXT:
            self.send_text(binding.value)
        elif binding.action_type == ActionType.COMMAND:
            if self._on_command:
                self._on_command(binding.value)
        elif binding.action_type == ActionType.CALLBACK:
            if callable(binding.value):
                binding.value()

    def send_key(self, key: str) -> None:
        if self._on_key:
            self._on_key(key)

    def send_key_combo(self, *keys: str) -> None:
        if self._on_combo:
            self._on_combo(keys)

    def send_text(self, text: str) -> None:
        if self._on_text:
            self._on_text(text)
