#!/usr/bin/env python3
"""
iTerm Bridge for Controller Emulator.

Connects the gamepad emulator to iTerm terminal sessions,
allowing you to control terminals with a game controller.

This module provides the bridge between the controller emulator
and the iTerm MCP server for real terminal control.
"""

import sys
import time
import json
import subprocess
from dataclasses import dataclass
from typing import Optional, Callable, Dict, Any
from threading import Thread, Event

from .emulator import GamepadEmulator, GamepadButton, DPadDirection
from .mapper import (
    ControllerMapper,
    ControllerProfile,
    ActionBinding,
    ActionType,
    Keys,
    create_terminal_navigation_profile,
    create_vim_profile,
)


@dataclass
class ITermSession:
    """Represents an iTerm session."""
    session_id: str
    name: str
    agent: Optional[str] = None


class ITermBridge:
    """
    Bridge between controller emulator and iTerm.

    Uses escape sequences and terminal control codes to send
    input directly to an iTerm session.
    """

    # Terminal escape sequences for special keys
    KEY_SEQUENCES = {
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

    def __init__(
        self,
        session_id: Optional[str] = None,
        agent_name: Optional[str] = None,
    ):
        """
        Initialize the bridge.

        Args:
            session_id: iTerm session ID to control
            agent_name: Agent name to target (alternative to session_id)
        """
        self.session_id = session_id
        self.agent_name = agent_name

        # Controller setup
        self.gamepad = GamepadEmulator("iTerm Controller")
        self.mapper = ControllerMapper(self.gamepad)

        # Available profiles
        self.profiles = {
            'terminal': create_terminal_navigation_profile(),
            'vim': create_vim_profile(),
        }
        self.current_profile = 'terminal'

        # Set up the mapper
        self.mapper.set_executor(self._execute_action)
        self.mapper.load_profile(self.profiles[self.current_profile])
        self.mapper.start()

        # State
        self._running = False
        self._event_log = []

    def set_target(self, session_id: Optional[str] = None, agent_name: Optional[str] = None):
        """Set the target iTerm session."""
        self.session_id = session_id
        self.agent_name = agent_name

    def switch_profile(self, profile_name: str) -> bool:
        """Switch to a different control profile."""
        if profile_name not in self.profiles:
            return False
        self.current_profile = profile_name
        self.mapper.load_profile(self.profiles[profile_name])
        self._log(f"Switched to profile: {profile_name}")
        return True

    def _execute_action(self, binding: ActionBinding) -> None:
        """Execute an action by sending to iTerm."""
        if binding.action_type == ActionType.KEY:
            self._send_key(binding.value)
        elif binding.action_type == ActionType.KEY_COMBO:
            self._send_combo(binding.value)
        elif binding.action_type == ActionType.TEXT:
            self._send_text(binding.value)
        elif binding.action_type == ActionType.COMMAND:
            self._send_text(binding.value + '\n')
        elif binding.action_type == ActionType.CALLBACK:
            if callable(binding.value):
                binding.value()

        self._log(f"Action: {binding.description or binding.value}")

    def _send_key(self, key: str) -> None:
        """Send a single key to the terminal."""
        sequence = self.KEY_SEQUENCES.get(key, key)
        self._write_to_session(sequence)

    def _send_combo(self, keys: tuple) -> None:
        """Send a key combination to the terminal."""
        modifiers = set()
        main_key = None

        for key in keys:
            if key in (Keys.SHIFT, Keys.CONTROL, Keys.ALT, Keys.COMMAND):
                modifiers.add(key)
            else:
                main_key = key

        if not main_key:
            return

        # Handle Ctrl+key combinations
        if Keys.CONTROL in modifiers and len(main_key) == 1 and main_key.isalpha():
            # Ctrl+letter = letter - 64
            ctrl_char = chr(ord(main_key.upper()) - 64)
            self._write_to_session(ctrl_char)
            return

        # Handle Shift+Tab
        if Keys.SHIFT in modifiers and main_key == Keys.TAB:
            self._write_to_session('\x1b[Z')
            return

        # Default: just send the main key
        self._send_key(main_key)

    def _send_text(self, text: str) -> None:
        """Send text to the terminal."""
        self._write_to_session(text)

    def _write_to_session(self, content: str) -> None:
        """
        Write content to the iTerm session.

        This method uses AppleScript to write to iTerm since we can't
        directly call MCP from within Python. In a real integration,
        this would use the MCP write_to_sessions tool.
        """
        if not self.session_id and not self.agent_name:
            print(f"[No target] Would send: {repr(content)}")
            return

        # Escape special characters for AppleScript
        escaped = content.replace('\\', '\\\\').replace('"', '\\"')

        # Build AppleScript to write to specific session
        script = f'''
        tell application "iTerm"
            tell current window
                repeat with aTab in tabs
                    repeat with aSession in sessions of aTab
                        if id of aSession is "{self.session_id}" then
                            tell aSession
                                write text "{escaped}" newline no
                            end tell
                            return
                        end if
                    end repeat
                end repeat
            end tell
        end tell
        '''

        try:
            subprocess.run(
                ['osascript', '-e', script],
                capture_output=True,
                timeout=2
            )
        except Exception as e:
            self._log(f"Error writing to session: {e}")

    def _log(self, message: str) -> None:
        """Log an event."""
        timestamp = time.strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}"
        self._event_log.append(entry)
        if len(self._event_log) > 100:
            self._event_log = self._event_log[-50:]


class GamepadTerminalController:
    """
    High-level controller for terminal navigation with a gamepad.

    Provides an easy-to-use interface for controlling terminals
    with the software gamepad emulator.
    """

    def __init__(self, session_id: str):
        """
        Initialize the controller.

        Args:
            session_id: iTerm session ID to control
        """
        self.bridge = ITermBridge(session_id=session_id)
        self.gamepad = self.bridge.gamepad

        # Quick reference to common actions
        self._setup_convenience_methods()

    def _setup_convenience_methods(self):
        """Set up convenience methods for common actions."""
        pass  # Methods are already available via self.gamepad

    # === Navigation ===

    def up(self):
        """Navigate up."""
        self.gamepad.set_dpad(DPadDirection.UP)
        time.sleep(0.05)
        self.gamepad.set_dpad(DPadDirection.NONE)

    def down(self):
        """Navigate down."""
        self.gamepad.set_dpad(DPadDirection.DOWN)
        time.sleep(0.05)
        self.gamepad.set_dpad(DPadDirection.NONE)

    def left(self):
        """Navigate left."""
        self.gamepad.set_dpad(DPadDirection.LEFT)
        time.sleep(0.05)
        self.gamepad.set_dpad(DPadDirection.NONE)

    def right(self):
        """Navigate right."""
        self.gamepad.set_dpad(DPadDirection.RIGHT)
        time.sleep(0.05)
        self.gamepad.set_dpad(DPadDirection.NONE)

    # === Actions ===

    def confirm(self):
        """Confirm / Enter."""
        self.gamepad.tap(GamepadButton.A, duration=0.05)

    def cancel(self):
        """Cancel / Escape."""
        self.gamepad.tap(GamepadButton.B, duration=0.05)

    def tab(self):
        """Tab / Autocomplete."""
        self.gamepad.tap(GamepadButton.Y, duration=0.05)

    def backspace(self):
        """Backspace."""
        self.gamepad.tap(GamepadButton.X, duration=0.05)

    def interrupt(self):
        """Ctrl+C - Interrupt."""
        self.gamepad.tap(GamepadButton.START, duration=0.05)

    # === Profile ===

    def switch_to_vim(self):
        """Switch to Vim control profile."""
        self.bridge.switch_profile('vim')

    def switch_to_terminal(self):
        """Switch to terminal navigation profile."""
        self.bridge.switch_profile('terminal')

    # === Sequences ===

    def type_command(self, cmd: str):
        """Type a command (doesn't execute)."""
        for char in cmd:
            self.bridge._send_text(char)
            time.sleep(0.02)

    def run_command(self, cmd: str):
        """Type and execute a command."""
        self.type_command(cmd)
        time.sleep(0.1)
        self.confirm()


def create_demo_profile() -> ControllerProfile:
    """Create a demo profile with visual feedback."""
    profile = ControllerProfile(
        name="Demo Mode",
        description="Demo profile with console output"
    )

    # Face buttons with print feedback
    profile.bind_button(GamepadButton.A, ActionBinding(
        ActionType.KEY, Keys.ENTER, "A -> Enter"
    ))
    profile.bind_button(GamepadButton.B, ActionBinding(
        ActionType.KEY, Keys.ESCAPE, "B -> Escape"
    ))
    profile.bind_button(GamepadButton.X, ActionBinding(
        ActionType.KEY, Keys.BACKSPACE, "X -> Backspace"
    ))
    profile.bind_button(GamepadButton.Y, ActionBinding(
        ActionType.KEY, Keys.TAB, "Y -> Tab"
    ))

    # D-pad
    profile.bind_dpad(DPadDirection.UP, ActionBinding(
        ActionType.KEY, Keys.UP, "D-Up -> Arrow Up"
    ))
    profile.bind_dpad(DPadDirection.DOWN, ActionBinding(
        ActionType.KEY, Keys.DOWN, "D-Down -> Arrow Down"
    ))
    profile.bind_dpad(DPadDirection.LEFT, ActionBinding(
        ActionType.KEY, Keys.LEFT, "D-Left -> Arrow Left"
    ))
    profile.bind_dpad(DPadDirection.RIGHT, ActionBinding(
        ActionType.KEY, Keys.RIGHT, "D-Right -> Arrow Right"
    ))

    # Shoulder buttons
    profile.bind_button(GamepadButton.LB, ActionBinding(
        ActionType.KEY_COMBO, (Keys.SHIFT, Keys.TAB), "LB -> Shift+Tab"
    ))
    profile.bind_button(GamepadButton.RB, ActionBinding(
        ActionType.KEY, Keys.TAB, "RB -> Tab"
    ))

    # Start/Select
    profile.bind_button(GamepadButton.START, ActionBinding(
        ActionType.KEY_COMBO, (Keys.CONTROL, 'c'), "Start -> Ctrl+C"
    ))
    profile.bind_button(GamepadButton.SELECT, ActionBinding(
        ActionType.KEY_COMBO, (Keys.CONTROL, 'd'), "Select -> Ctrl+D"
    ))

    return profile


def main():
    """Demo entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Gamepad Terminal Controller")
    parser.add_argument(
        '--session', '-s',
        help='iTerm session ID to control'
    )
    parser.add_argument(
        '--agent', '-a',
        default='gamepad-demo',
        help='Agent name to control'
    )
    parser.add_argument(
        '--list', '-l',
        action='store_true',
        help='List available sessions'
    )

    args = parser.parse_args()

    if args.list:
        print("Use iTerm MCP list_sessions to see available sessions")
        return

    session_id = args.session

    if not session_id:
        print("Gamepad Terminal Controller")
        print("=" * 40)
        print()
        print("This controller needs an iTerm session ID to control.")
        print("The session 'gamepad-demo' has been created for you.")
        print()
        print("Usage:")
        print("  from selectron.controller.iterm_bridge import GamepadTerminalController")
        print("  ctrl = GamepadTerminalController('SESSION_ID')")
        print("  ctrl.up()      # Navigate up")
        print("  ctrl.confirm() # Press enter")
        print("  ctrl.run_command('ls -la')  # Type and run command")
        return

    print(f"Connecting to session: {session_id}")
    controller = GamepadTerminalController(session_id)

    print("Controller ready! Use the gamepad to control the terminal.")
    print("Press Ctrl+C to exit.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting...")


if __name__ == '__main__':
    main()
