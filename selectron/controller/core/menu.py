#!/usr/bin/env python3
"""
Interactive menu system for gamepad control.

Provides notification dialogs and multiple-choice menus that can be
navigated using the gamepad controller.
"""

import sys
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional, Tuple, Any, Union
from threading import Event

from .emulator import GamepadEmulator, GamepadButton, DPadDirection


class MenuResult(Enum):
    """Result of a menu interaction."""
    SELECTED = auto()    # User made a selection
    CANCELLED = auto()   # User cancelled (B button)
    TIMEOUT = auto()     # Menu timed out


@dataclass
class MenuOption:
    """A single menu option."""
    label: str
    value: Any = None
    description: str = ""
    enabled: bool = True
    icon: str = ""

    def __post_init__(self):
        if self.value is None:
            self.value = self.label


@dataclass
class MenuConfig:
    """Configuration for menu display."""
    title: str = ""
    prompt: str = "Select an option:"
    show_index: bool = True
    show_description: bool = True
    allow_cancel: bool = True
    multi_select: bool = False
    min_selections: int = 0
    max_selections: int = 0  # 0 = unlimited
    timeout: float = 0  # 0 = no timeout

    # Visual
    selected_prefix: str = "> "
    unselected_prefix: str = "  "
    checked_prefix: str = "[x] "
    unchecked_prefix: str = "[ ] "
    disabled_prefix: str = "  # "


# ANSI escape codes
class ANSI:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    UNDERLINE = '\033[4m'

    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'

    BG_BLACK = '\033[40m'
    BG_WHITE = '\033[47m'
    BG_BLUE = '\033[44m'

    CLEAR_LINE = '\033[2K'
    CURSOR_UP = '\033[A'
    CURSOR_DOWN = '\033[B'
    HIDE_CURSOR = '\033[?25l'
    SHOW_CURSOR = '\033[?25h'

    @staticmethod
    def move_up(n: int = 1) -> str:
        return f'\033[{n}A'

    @staticmethod
    def move_to_col(col: int) -> str:
        return f'\033[{col}G'


class GamepadMenu:
    """
    Interactive menu controlled by gamepad.

    Example usage:
        menu = GamepadMenu(gamepad)

        # Simple selection
        result, choice = menu.select(
            "Choose a profile:",
            ["Terminal", "Vim", "Custom"]
        )

        # Multi-select
        result, choices = menu.multi_select(
            "Select features to enable:",
            ["Autocomplete", "Syntax highlighting", "Line numbers"],
            min_selections=1
        )

        # Confirmation
        if menu.confirm("Are you sure?"):
            do_something()
    """

    def __init__(self, gamepad: GamepadEmulator):
        self.gamepad = gamepad
        self._current_index = 0
        self._selected_indices: set = set()
        self._result: Optional[MenuResult] = None
        self._done = Event()

        # Store original callbacks
        self._original_button_callbacks = []
        self._original_dpad_callbacks = []

    def _setup_callbacks(self, config: MenuConfig, options: List[MenuOption]):
        """Set up gamepad callbacks for menu navigation."""
        # Store originals
        self._original_button_callbacks = self.gamepad._button_callbacks.copy()
        self._original_dpad_callbacks = self.gamepad._dpad_callbacks.copy()

        # Clear and set new
        self.gamepad._button_callbacks.clear()
        self.gamepad._dpad_callbacks.clear()

        def on_button(button: GamepadButton, pressed: bool):
            if not pressed:
                return

            if button == GamepadButton.A:
                self._on_select(config, options)
            elif button == GamepadButton.B and config.allow_cancel:
                self._result = MenuResult.CANCELLED
                self._done.set()
            elif button in (GamepadButton.START, GamepadButton.Y):
                # Alternative confirm for multi-select
                if config.multi_select:
                    self._on_confirm(config)

        def on_dpad(direction: DPadDirection):
            if direction == DPadDirection.UP:
                self._move_selection(-1, options)
            elif direction == DPadDirection.DOWN:
                self._move_selection(1, options)

        self.gamepad.on_button(on_button)
        self.gamepad.on_dpad(on_dpad)

    def _restore_callbacks(self):
        """Restore original gamepad callbacks."""
        self.gamepad._button_callbacks = self._original_button_callbacks
        self.gamepad._dpad_callbacks = self._original_dpad_callbacks

    def _move_selection(self, delta: int, options: List[MenuOption]):
        """Move selection up or down."""
        new_index = self._current_index + delta

        # Find next enabled option
        while 0 <= new_index < len(options):
            if options[new_index].enabled:
                self._current_index = new_index
                break
            new_index += delta

    def _on_select(self, config: MenuConfig, options: List[MenuOption]):
        """Handle A button press."""
        if not options[self._current_index].enabled:
            return

        if config.multi_select:
            # Toggle selection
            if self._current_index in self._selected_indices:
                self._selected_indices.remove(self._current_index)
            else:
                if config.max_selections == 0 or len(self._selected_indices) < config.max_selections:
                    self._selected_indices.add(self._current_index)
        else:
            # Single select - done
            self._selected_indices = {self._current_index}
            self._result = MenuResult.SELECTED
            self._done.set()

    def _on_confirm(self, config: MenuConfig):
        """Handle confirmation in multi-select mode."""
        if len(self._selected_indices) >= config.min_selections:
            self._result = MenuResult.SELECTED
            self._done.set()

    def _render_menu(
        self,
        options: List[MenuOption],
        config: MenuConfig,
        clear_previous: bool = False,
        line_count: int = 0
    ) -> int:
        """Render the menu to stdout. Returns number of lines rendered."""
        lines = []

        # Title
        if config.title:
            lines.append(f"{ANSI.BOLD}{config.title}{ANSI.RESET}")
            lines.append("")

        # Prompt
        if config.prompt:
            lines.append(config.prompt)

        # Options
        for i, opt in enumerate(options):
            is_current = i == self._current_index
            is_selected = i in self._selected_indices

            # Build prefix
            if not opt.enabled:
                prefix = config.disabled_prefix
                color = ANSI.DIM
            elif config.multi_select:
                check = config.checked_prefix if is_selected else config.unchecked_prefix
                cursor = config.selected_prefix if is_current else config.unselected_prefix
                prefix = cursor[:-2] + check  # Combine cursor and checkbox
                color = ANSI.GREEN if is_current else ANSI.RESET
            else:
                prefix = config.selected_prefix if is_current else config.unselected_prefix
                color = ANSI.GREEN if is_current else ANSI.RESET

            # Build label
            label = opt.label
            if opt.icon:
                label = f"{opt.icon} {label}"
            if config.show_index:
                label = f"{i + 1}. {label}"

            line = f"{color}{prefix}{label}{ANSI.RESET}"
            lines.append(line)

            # Description
            if config.show_description and opt.description and is_current:
                lines.append(f"   {ANSI.DIM}{opt.description}{ANSI.RESET}")

        # Footer for multi-select
        if config.multi_select:
            lines.append("")
            selected_count = len(self._selected_indices)
            if config.min_selections > 0:
                lines.append(f"{ANSI.DIM}Selected: {selected_count} (min: {config.min_selections}){ANSI.RESET}")
            else:
                lines.append(f"{ANSI.DIM}Selected: {selected_count}{ANSI.RESET}")
            lines.append(f"{ANSI.DIM}[A] Toggle  [Start/Y] Confirm  [B] Cancel{ANSI.RESET}")
        else:
            lines.append("")
            lines.append(f"{ANSI.DIM}[A] Select  [B] Cancel  [D-pad] Navigate{ANSI.RESET}")

        # Clear previous render
        if clear_previous and line_count > 0:
            sys.stdout.write(ANSI.move_up(line_count))
            for _ in range(line_count):
                sys.stdout.write(ANSI.CLEAR_LINE + '\n')
            sys.stdout.write(ANSI.move_up(line_count))

        # Print
        for line in lines:
            print(line)

        sys.stdout.flush()
        return len(lines)

    def select(
        self,
        prompt: str,
        options: Union[List[str], List[MenuOption]],
        title: str = "",
        default: int = 0,
        timeout: float = 0,
    ) -> Tuple[MenuResult, Optional[Any]]:
        """
        Show a single-selection menu.

        Args:
            prompt: The question/prompt to show
            options: List of option strings or MenuOption objects
            title: Optional title above the menu
            default: Default selected index
            timeout: Timeout in seconds (0 = no timeout)

        Returns:
            Tuple of (MenuResult, selected_value or None)
        """
        # Convert strings to MenuOptions
        menu_options = [
            MenuOption(label=o) if isinstance(o, str) else o
            for o in options
        ]

        config = MenuConfig(
            title=title,
            prompt=prompt,
            multi_select=False,
            timeout=timeout,
        )

        # Initialize state
        self._current_index = default
        self._selected_indices = set()
        self._result = None
        self._done.clear()

        # Set up callbacks
        self._setup_callbacks(config, menu_options)

        try:
            print(ANSI.HIDE_CURSOR)
            line_count = self._render_menu(menu_options, config)

            # Wait for input (with refresh loop)
            start_time = time.time()
            last_index = self._current_index

            while not self._done.is_set():
                # Check timeout
                if timeout > 0 and time.time() - start_time > timeout:
                    self._result = MenuResult.TIMEOUT
                    break

                # Re-render if selection changed
                if self._current_index != last_index:
                    line_count = self._render_menu(
                        menu_options, config,
                        clear_previous=True, line_count=line_count
                    )
                    last_index = self._current_index

                time.sleep(0.05)

            print(ANSI.SHOW_CURSOR)

            if self._result == MenuResult.SELECTED:
                return (MenuResult.SELECTED, menu_options[self._current_index].value)
            else:
                return (self._result, None)

        finally:
            self._restore_callbacks()
            print(ANSI.SHOW_CURSOR)

    def multi_select(
        self,
        prompt: str,
        options: Union[List[str], List[MenuOption]],
        title: str = "",
        min_selections: int = 0,
        max_selections: int = 0,
        default_selected: Optional[List[int]] = None,
        timeout: float = 0,
    ) -> Tuple[MenuResult, List[Any]]:
        """
        Show a multi-selection menu.

        Args:
            prompt: The question/prompt to show
            options: List of option strings or MenuOption objects
            title: Optional title above the menu
            min_selections: Minimum required selections
            max_selections: Maximum allowed selections (0 = unlimited)
            default_selected: Indices of pre-selected options
            timeout: Timeout in seconds (0 = no timeout)

        Returns:
            Tuple of (MenuResult, list of selected values)
        """
        # Convert strings to MenuOptions
        menu_options = [
            MenuOption(label=o) if isinstance(o, str) else o
            for o in options
        ]

        config = MenuConfig(
            title=title,
            prompt=prompt,
            multi_select=True,
            min_selections=min_selections,
            max_selections=max_selections,
            timeout=timeout,
        )

        # Initialize state
        self._current_index = 0
        self._selected_indices = set(default_selected or [])
        self._result = None
        self._done.clear()

        # Set up callbacks
        self._setup_callbacks(config, menu_options)

        try:
            print(ANSI.HIDE_CURSOR)
            line_count = self._render_menu(menu_options, config)

            # Wait for input
            start_time = time.time()
            last_state = (self._current_index, frozenset(self._selected_indices))

            while not self._done.is_set():
                if timeout > 0 and time.time() - start_time > timeout:
                    self._result = MenuResult.TIMEOUT
                    break

                current_state = (self._current_index, frozenset(self._selected_indices))
                if current_state != last_state:
                    line_count = self._render_menu(
                        menu_options, config,
                        clear_previous=True, line_count=line_count
                    )
                    last_state = current_state

                time.sleep(0.05)

            print(ANSI.SHOW_CURSOR)

            if self._result == MenuResult.SELECTED:
                selected_values = [
                    menu_options[i].value
                    for i in sorted(self._selected_indices)
                ]
                return (MenuResult.SELECTED, selected_values)
            else:
                return (self._result, [])

        finally:
            self._restore_callbacks()
            print(ANSI.SHOW_CURSOR)

    def confirm(
        self,
        message: str,
        default: bool = False,
        timeout: float = 0,
    ) -> bool:
        """
        Show a yes/no confirmation dialog.

        Args:
            message: The confirmation message
            default: Default selection (True = Yes, False = No)
            timeout: Timeout in seconds (returns default on timeout)

        Returns:
            True if confirmed, False otherwise
        """
        options = [
            MenuOption(label="Yes", value=True),
            MenuOption(label="No", value=False),
        ]

        result, value = self.select(
            prompt=message,
            options=options,
            default=0 if default else 1,
            timeout=timeout,
        )

        if result == MenuResult.SELECTED:
            return value
        elif result == MenuResult.TIMEOUT:
            return default
        else:
            return False

    def notify(
        self,
        message: str,
        title: str = "Notice",
        style: str = "info",
        wait_for_dismiss: bool = True,
    ):
        """
        Show a notification message.

        Args:
            message: The message to display
            title: Notification title
            style: One of "info", "success", "warning", "error"
            wait_for_dismiss: If True, wait for A or B button
        """
        # Style colors
        styles = {
            'info': ANSI.BLUE,
            'success': ANSI.GREEN,
            'warning': ANSI.YELLOW,
            'error': ANSI.RED,
        }
        icons = {
            'info': 'ℹ️',
            'success': '✅',
            'warning': '⚠️',
            'error': '❌',
        }

        color = styles.get(style, ANSI.BLUE)
        icon = icons.get(style, 'ℹ️')

        # Render
        print()
        print(f"{color}{ANSI.BOLD}{icon} {title}{ANSI.RESET}")
        print(f"  {message}")

        if wait_for_dismiss:
            print(f"{ANSI.DIM}  Press [A] to continue...{ANSI.RESET}")
            print()

            # Wait for button
            dismissed = Event()

            original_callbacks = self.gamepad._button_callbacks.copy()
            self.gamepad._button_callbacks.clear()

            def on_button(button: GamepadButton, pressed: bool):
                if pressed and button in (GamepadButton.A, GamepadButton.B):
                    dismissed.set()

            self.gamepad.on_button(on_button)

            try:
                dismissed.wait()
            finally:
                self.gamepad._button_callbacks = original_callbacks
        else:
            print()


def demo():
    """Interactive demo of the menu system."""
    from .emulator import GamepadEmulator

    gamepad = GamepadEmulator("Menu Demo")
    menu = GamepadMenu(gamepad)

    print("Gamepad Menu System Demo")
    print("=" * 40)
    print()
    print("Since we're using a software emulator, use keyboard:")
    print("  Arrow Up/Down: Navigate")
    print("  Space: Select (A button)")
    print("  Escape: Cancel (B button)")
    print()

    # For demo, simulate with keyboard
    import threading

    def keyboard_to_gamepad():
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

                    if ch == '\x1b':
                        # Escape sequence
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
                            # Just escape
                            gamepad.tap(GamepadButton.B, 0.05)
                    elif ch == ' ':
                        gamepad.tap(GamepadButton.A, 0.05)
                    elif ch == '\r':
                        gamepad.tap(GamepadButton.START, 0.05)
                    elif ch == 'q':
                        break
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

    # Start keyboard listener
    kb_thread = threading.Thread(target=keyboard_to_gamepad, daemon=True)
    kb_thread.start()

    # Demo menu
    result, choice = menu.select(
        "Choose your profile:",
        [
            MenuOption("Terminal Navigation", "terminal", "Standard terminal controls"),
            MenuOption("Vim Mode", "vim", "Vim-style navigation"),
            MenuOption("Custom", "custom", "Create custom bindings"),
        ],
        title="Profile Selection"
    )

    if result == MenuResult.SELECTED:
        print(f"\nYou selected: {choice}")
    else:
        print(f"\nCancelled")


if __name__ == '__main__':
    demo()
