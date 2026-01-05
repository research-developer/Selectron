"""
Action executors for different targets.

Executors handle the actual sending of key presses, commands, etc.
to terminals, IDEs, or other targets.
"""

from abc import ABC, abstractmethod
from typing import Callable, Optional, Dict, Any
import subprocess
import platform

from .mapper import ActionBinding, ActionType, Keys


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


class AppleScriptExecutor(ActionExecutor):
    """
    Executor that uses AppleScript to send keys to the frontmost application.
    macOS only.
    """

    # Map our key constants to AppleScript key codes
    KEY_CODE_MAP = {
        Keys.UP: 126,
        Keys.DOWN: 125,
        Keys.LEFT: 123,
        Keys.RIGHT: 124,
        Keys.ENTER: 36,
        Keys.RETURN: 36,
        Keys.ESCAPE: 53,
        Keys.TAB: 48,
        Keys.BACKSPACE: 51,
        Keys.DELETE: 117,
        Keys.SPACE: 49,
        Keys.HOME: 115,
        Keys.END: 119,
        Keys.PAGE_UP: 116,
        Keys.PAGE_DOWN: 121,
    }

    # Modifier key names for AppleScript
    MODIFIER_MAP = {
        Keys.SHIFT: 'shift down',
        Keys.CONTROL: 'control down',
        Keys.ALT: 'option down',
        Keys.COMMAND: 'command down',
    }

    def __init__(self, target_app: Optional[str] = None):
        """
        Initialize the executor.

        Args:
            target_app: Specific app to target, or None for frontmost.
        """
        if platform.system() != 'Darwin':
            raise RuntimeError("AppleScriptExecutor only works on macOS")

        self.target_app = target_app

    def execute(self, binding: ActionBinding) -> None:
        if binding.action_type == ActionType.KEY:
            self.send_key(binding.value)
        elif binding.action_type == ActionType.KEY_COMBO:
            self.send_key_combo(*binding.value)
        elif binding.action_type == ActionType.TEXT:
            self.send_text(binding.value)
        elif binding.action_type == ActionType.COMMAND:
            # For commands, we type the command and press enter
            self.send_text(binding.value)
            self.send_key(Keys.ENTER)
        elif binding.action_type == ActionType.CALLBACK:
            if callable(binding.value):
                binding.value()

    def send_key(self, key: str) -> None:
        """Send a single key press."""
        if key in self.KEY_CODE_MAP:
            self._run_applescript(f'tell application "System Events" to key code {self.KEY_CODE_MAP[key]}')
        else:
            # Single character - use keystroke
            self._run_applescript(f'tell application "System Events" to keystroke "{key}"')

    def send_key_combo(self, *keys: str) -> None:
        """Send a key combination."""
        modifiers = []
        main_key = None

        for key in keys:
            if key in self.MODIFIER_MAP:
                modifiers.append(self.MODIFIER_MAP[key])
            else:
                main_key = key

        if not main_key:
            return

        modifier_str = ', '.join(modifiers) if modifiers else ''

        if main_key in self.KEY_CODE_MAP:
            if modifier_str:
                script = f'tell application "System Events" to key code {self.KEY_CODE_MAP[main_key]} using {{{modifier_str}}}'
            else:
                script = f'tell application "System Events" to key code {self.KEY_CODE_MAP[main_key]}'
        else:
            if modifier_str:
                script = f'tell application "System Events" to keystroke "{main_key}" using {{{modifier_str}}}'
            else:
                script = f'tell application "System Events" to keystroke "{main_key}"'

        self._run_applescript(script)

    def send_text(self, text: str) -> None:
        """Type a text string."""
        # Escape quotes
        escaped = text.replace('"', '\\"')
        self._run_applescript(f'tell application "System Events" to keystroke "{escaped}"')

    def _run_applescript(self, script: str) -> None:
        """Run an AppleScript command."""
        if self.target_app:
            # Activate the target app first
            full_script = f'''
            tell application "{self.target_app}" to activate
            delay 0.1
            {script}
            '''
        else:
            full_script = script

        try:
            subprocess.run(
                ['osascript', '-e', full_script],
                capture_output=True,
                check=True,
                timeout=5
            )
        except subprocess.CalledProcessError as e:
            print(f"AppleScript error: {e.stderr.decode()}")
        except subprocess.TimeoutExpired:
            print("AppleScript timeout")


class ITermExecutor(ActionExecutor):
    """
    Executor that sends input to a specific iTerm session.

    This integrates with the iTerm MCP server when available.
    For standalone use, it falls back to AppleScript.
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        mcp_write_fn: Optional[Callable] = None
    ):
        """
        Initialize the executor.

        Args:
            session_id: iTerm session ID to target
            agent_name: Agent name to target (alternative to session_id)
            mcp_write_fn: Function to write to session via MCP
                         (signature: write_fn(content, target) -> None)
        """
        self.session_id = session_id
        self.agent_name = agent_name
        self._mcp_write = mcp_write_fn

        # Fall back to AppleScript for iTerm
        if platform.system() == 'Darwin':
            self._fallback = AppleScriptExecutor(target_app="iTerm")
        else:
            self._fallback = PrintExecutor(prefix="[iTerm] ")

    def set_mcp_writer(self, write_fn: Callable) -> None:
        """Set the MCP write function for direct session control."""
        self._mcp_write = write_fn

    def execute(self, binding: ActionBinding) -> None:
        if binding.action_type == ActionType.KEY:
            self.send_key(binding.value)
        elif binding.action_type == ActionType.KEY_COMBO:
            self.send_key_combo(*binding.value)
        elif binding.action_type == ActionType.TEXT:
            self.send_text(binding.value)
        elif binding.action_type == ActionType.COMMAND:
            # Send command with enter
            self.send_text(binding.value + '\n')
        elif binding.action_type == ActionType.CALLBACK:
            if callable(binding.value):
                binding.value()

    def send_key(self, key: str) -> None:
        """Send a single key press."""
        if self._mcp_write:
            self._send_via_mcp(self._key_to_escape(key))
        else:
            self._fallback.send_key(key)

    def send_key_combo(self, *keys: str) -> None:
        """Send a key combination."""
        if self._mcp_write:
            # Convert combo to escape sequence
            escape_seq = self._combo_to_escape(keys)
            if escape_seq:
                self._send_via_mcp(escape_seq)
        else:
            self._fallback.send_key_combo(*keys)

    def send_text(self, text: str) -> None:
        """Type a text string."""
        if self._mcp_write:
            self._send_via_mcp(text)
        else:
            self._fallback.send_text(text)

    def _send_via_mcp(self, content: str) -> None:
        """Send content via MCP write function."""
        target = {}
        if self.session_id:
            target['session_id'] = self.session_id
        elif self.agent_name:
            target['agent'] = self.agent_name

        try:
            self._mcp_write(content, target)
        except Exception as e:
            print(f"MCP write error: {e}")

    def _key_to_escape(self, key: str) -> str:
        """Convert a key to its terminal escape sequence."""
        escape_map = {
            Keys.UP: '\x1b[A',
            Keys.DOWN: '\x1b[B',
            Keys.RIGHT: '\x1b[C',
            Keys.LEFT: '\x1b[D',
            Keys.ENTER: '\r',
            Keys.RETURN: '\r',
            Keys.ESCAPE: '\x1b',
            Keys.TAB: '\t',
            Keys.BACKSPACE: '\x7f',
            Keys.DELETE: '\x1b[3~',
            Keys.HOME: '\x1b[H',
            Keys.END: '\x1b[F',
            Keys.PAGE_UP: '\x1b[5~',
            Keys.PAGE_DOWN: '\x1b[6~',
            Keys.SPACE: ' ',
        }
        return escape_map.get(key, key)

    def _combo_to_escape(self, keys: tuple) -> Optional[str]:
        """Convert a key combo to terminal escape sequence."""
        modifiers = set()
        main_key = None

        for key in keys:
            if key in (Keys.SHIFT, Keys.CONTROL, Keys.ALT, Keys.COMMAND):
                modifiers.add(key)
            else:
                main_key = key

        if not main_key:
            return None

        # Handle Ctrl+key combinations
        if Keys.CONTROL in modifiers and len(main_key) == 1:
            # Ctrl+letter = letter - 64 (or - 96 for lowercase)
            if main_key.isalpha():
                return chr(ord(main_key.upper()) - 64)

        # Handle other common combos
        if modifiers == {Keys.CONTROL, Keys.SHIFT} and main_key == Keys.TAB:
            return '\x1b[Z'  # Shift+Tab

        # Fall back to just the main key
        return self._key_to_escape(main_key)


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
