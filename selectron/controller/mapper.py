"""
Controller-to-action mapper.

Maps gamepad inputs to configurable actions like keyboard shortcuts,
terminal commands, or custom callbacks.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Dict, List, Optional, Union, Any
import time

from .emulator import (
    GamepadEmulator,
    GamepadButton,
    DPadDirection,
    GamepadState,
)


class ActionType(Enum):
    """Types of actions that can be triggered."""
    KEY = auto()          # Single key press
    KEY_COMBO = auto()    # Key combination (e.g., Cmd+C)
    TEXT = auto()         # Type text string
    COMMAND = auto()      # Terminal command
    CALLBACK = auto()     # Custom Python callback
    MACRO = auto()        # Sequence of actions


@dataclass
class ActionBinding:
    """
    Binding between a controller input and an action.
    """
    action_type: ActionType
    value: Any  # The action value (key, command, callback, etc.)
    description: str = ""

    # Modifiers for button actions
    on_press: bool = True    # Trigger on press
    on_release: bool = False  # Trigger on release
    repeat: bool = False      # Repeat while held
    repeat_delay: float = 0.5  # Initial delay before repeat
    repeat_rate: float = 0.1   # Rate of repeat

    def __repr__(self) -> str:
        return f"ActionBinding({self.action_type.name}, {self.value!r})"


# Common key mappings
class Keys:
    """Common key constants for action bindings."""
    # Navigation
    UP = 'up'
    DOWN = 'down'
    LEFT = 'left'
    RIGHT = 'right'

    # Editing
    ENTER = 'enter'
    RETURN = 'return'
    ESCAPE = 'escape'
    TAB = 'tab'
    BACKSPACE = 'backspace'
    DELETE = 'delete'
    SPACE = 'space'

    # Modifiers
    SHIFT = 'shift'
    CONTROL = 'control'
    ALT = 'alt'
    COMMAND = 'command'

    # Special
    HOME = 'home'
    END = 'end'
    PAGE_UP = 'pageup'
    PAGE_DOWN = 'pagedown'


@dataclass
class ControllerProfile:
    """
    A complete mapping profile for a controller.

    Profiles allow switching between different mapping schemes
    (e.g., navigation mode, editing mode, gaming mode).
    """
    name: str
    description: str = ""

    # Button mappings
    button_bindings: Dict[GamepadButton, ActionBinding] = field(default_factory=dict)

    # D-pad mappings
    dpad_bindings: Dict[DPadDirection, ActionBinding] = field(default_factory=dict)

    # Stick mappings (for threshold-based digital actions)
    left_stick_up: Optional[ActionBinding] = None
    left_stick_down: Optional[ActionBinding] = None
    left_stick_left: Optional[ActionBinding] = None
    left_stick_right: Optional[ActionBinding] = None

    right_stick_up: Optional[ActionBinding] = None
    right_stick_down: Optional[ActionBinding] = None
    right_stick_left: Optional[ActionBinding] = None
    right_stick_right: Optional[ActionBinding] = None

    # Trigger thresholds
    left_trigger_binding: Optional[ActionBinding] = None
    right_trigger_binding: Optional[ActionBinding] = None

    # Stick threshold for digital conversion
    stick_threshold: float = 0.5

    def bind_button(self, button: GamepadButton, binding: ActionBinding) -> 'ControllerProfile':
        """Bind an action to a button. Returns self for chaining."""
        self.button_bindings[button] = binding
        return self

    def bind_dpad(self, direction: DPadDirection, binding: ActionBinding) -> 'ControllerProfile':
        """Bind an action to a D-pad direction. Returns self for chaining."""
        self.dpad_bindings[direction] = binding
        return self


class ControllerMapper:
    """
    Maps controller inputs to actions based on the active profile.

    Example usage:
        gamepad = GamepadEmulator()
        mapper = ControllerMapper(gamepad)

        # Create a profile
        profile = ControllerProfile("Terminal Navigation")
        profile.bind_button(
            GamepadButton.A,
            ActionBinding(ActionType.KEY, Keys.ENTER, "Confirm/Enter")
        )
        profile.bind_dpad(
            DPadDirection.UP,
            ActionBinding(ActionType.KEY, Keys.UP, "Move up")
        )

        mapper.load_profile(profile)
        mapper.start()

        # Now controller inputs will trigger the mapped actions
    """

    def __init__(self, gamepad: GamepadEmulator):
        self.gamepad = gamepad
        self._active_profile: Optional[ControllerProfile] = None
        self._profiles: Dict[str, ControllerProfile] = {}
        self._running = False

        # Action executor - can be overridden for different targets
        self._executor: Optional[Callable[[ActionBinding], None]] = None

        # State tracking for repeat functionality
        self._held_buttons: Dict[GamepadButton, float] = {}  # button -> press time
        self._last_repeat: Dict[GamepadButton, float] = {}   # button -> last repeat time

        # Stick state for digital conversion
        self._left_stick_state = {'up': False, 'down': False, 'left': False, 'right': False}
        self._right_stick_state = {'up': False, 'down': False, 'left': False, 'right': False}

        # Event log for debugging
        self._event_log: List[str] = []
        self._log_events = True

    @property
    def active_profile(self) -> Optional[ControllerProfile]:
        """Get the currently active profile."""
        return self._active_profile

    def set_executor(self, executor: Callable[[ActionBinding], None]) -> None:
        """
        Set the action executor.

        The executor is called whenever an action should be performed.
        This allows plugging in different backends (terminal, IDE, etc.).
        """
        self._executor = executor

    def add_profile(self, profile: ControllerProfile) -> None:
        """Add a profile to the mapper."""
        self._profiles[profile.name] = profile

    def load_profile(self, profile: Union[str, ControllerProfile]) -> None:
        """Load and activate a profile."""
        if isinstance(profile, str):
            if profile not in self._profiles:
                raise ValueError(f"Profile '{profile}' not found")
            self._active_profile = self._profiles[profile]
        else:
            self._active_profile = profile
            self._profiles[profile.name] = profile

        self._log(f"Loaded profile: {self._active_profile.name}")

    def start(self) -> None:
        """Start listening to controller events and mapping to actions."""
        if self._running:
            return

        self._running = True

        # Register callbacks with the gamepad
        self.gamepad.on_button(self._handle_button)
        self.gamepad.on_dpad(self._handle_dpad)
        self.gamepad.on_left_stick(self._handle_left_stick)
        self.gamepad.on_right_stick(self._handle_right_stick)
        self.gamepad.on_left_trigger(self._handle_left_trigger)
        self.gamepad.on_right_trigger(self._handle_right_trigger)

        self._log("Controller mapper started")

    def stop(self) -> None:
        """Stop listening to controller events."""
        self._running = False
        self._held_buttons.clear()
        self._log("Controller mapper stopped")

    def _handle_button(self, button: GamepadButton, pressed: bool) -> None:
        """Handle button press/release events."""
        if not self._active_profile:
            return

        binding = self._active_profile.button_bindings.get(button)
        if not binding:
            self._log(f"No binding for {button.name}")
            return

        if pressed:
            self._held_buttons[button] = time.time()
            if binding.on_press:
                self._execute(binding)
                self._log(f"Button {button.name} -> {binding.description or binding.value}")
        else:
            self._held_buttons.pop(button, None)
            self._last_repeat.pop(button, None)
            if binding.on_release:
                self._execute(binding)

    def _handle_dpad(self, direction: DPadDirection) -> None:
        """Handle D-pad direction changes."""
        if not self._active_profile:
            return

        if direction == DPadDirection.NONE:
            return

        binding = self._active_profile.dpad_bindings.get(direction)
        if binding:
            self._execute(binding)
            self._log(f"D-pad {direction.name} -> {binding.description or binding.value}")

    def _handle_left_stick(self, x: float, y: float) -> None:
        """Handle left stick movement, converting to digital actions."""
        if not self._active_profile:
            return

        threshold = self._active_profile.stick_threshold

        # Check each direction
        self._check_stick_axis(
            y, threshold, 'up', 'down',
            self._left_stick_state,
            self._active_profile.left_stick_up,
            self._active_profile.left_stick_down,
            "Left stick"
        )
        self._check_stick_axis(
            x, threshold, 'right', 'left',
            self._left_stick_state,
            self._active_profile.left_stick_right,
            self._active_profile.left_stick_left,
            "Left stick"
        )

    def _handle_right_stick(self, x: float, y: float) -> None:
        """Handle right stick movement, converting to digital actions."""
        if not self._active_profile:
            return

        threshold = self._active_profile.stick_threshold

        self._check_stick_axis(
            y, threshold, 'up', 'down',
            self._right_stick_state,
            self._active_profile.right_stick_up,
            self._active_profile.right_stick_down,
            "Right stick"
        )
        self._check_stick_axis(
            x, threshold, 'right', 'left',
            self._right_stick_state,
            self._active_profile.right_stick_right,
            self._active_profile.right_stick_left,
            "Right stick"
        )

    def _check_stick_axis(
        self,
        value: float,
        threshold: float,
        pos_dir: str,
        neg_dir: str,
        state: Dict[str, bool],
        pos_binding: Optional[ActionBinding],
        neg_binding: Optional[ActionBinding],
        stick_name: str
    ) -> None:
        """Check stick axis and trigger actions when crossing threshold."""
        # Positive direction
        if value > threshold and not state[pos_dir]:
            state[pos_dir] = True
            if pos_binding:
                self._execute(pos_binding)
                self._log(f"{stick_name} {pos_dir} -> {pos_binding.description or pos_binding.value}")
        elif value <= threshold:
            state[pos_dir] = False

        # Negative direction
        if value < -threshold and not state[neg_dir]:
            state[neg_dir] = True
            if neg_binding:
                self._execute(neg_binding)
                self._log(f"{stick_name} {neg_dir} -> {neg_binding.description or neg_binding.value}")
        elif value >= -threshold:
            state[neg_dir] = False

    def _handle_left_trigger(self, value: float) -> None:
        """Handle left trigger changes."""
        if not self._active_profile or not self._active_profile.left_trigger_binding:
            return

        if value > 0.5:  # Threshold
            self._execute(self._active_profile.left_trigger_binding)

    def _handle_right_trigger(self, value: float) -> None:
        """Handle right trigger changes."""
        if not self._active_profile or not self._active_profile.right_trigger_binding:
            return

        if value > 0.5:  # Threshold
            self._execute(self._active_profile.right_trigger_binding)

    def _execute(self, binding: ActionBinding) -> None:
        """Execute an action binding."""
        if self._executor:
            try:
                self._executor(binding)
            except Exception as e:
                self._log(f"Error executing action: {e}")
        else:
            # Default: just log
            self._log(f"Action (no executor): {binding}")

    def _log(self, message: str) -> None:
        """Log an event."""
        if self._log_events:
            timestamp = time.strftime("%H:%M:%S")
            entry = f"[{timestamp}] {message}"
            self._event_log.append(entry)
            # Keep log bounded
            if len(self._event_log) > 1000:
                self._event_log = self._event_log[-500:]

    def get_event_log(self, limit: int = 50) -> List[str]:
        """Get recent events from the log."""
        return self._event_log[-limit:]

    def clear_event_log(self) -> None:
        """Clear the event log."""
        self._event_log.clear()


# === Preset Profiles ===

def create_terminal_navigation_profile() -> ControllerProfile:
    """Create a profile optimized for terminal/shell navigation."""
    profile = ControllerProfile(
        name="Terminal Navigation",
        description="Navigate and interact with terminal applications"
    )

    # Face buttons
    profile.bind_button(GamepadButton.A, ActionBinding(
        ActionType.KEY, Keys.ENTER, "Confirm / Enter"
    ))
    profile.bind_button(GamepadButton.B, ActionBinding(
        ActionType.KEY, Keys.ESCAPE, "Cancel / Escape"
    ))
    profile.bind_button(GamepadButton.X, ActionBinding(
        ActionType.KEY, Keys.BACKSPACE, "Backspace"
    ))
    profile.bind_button(GamepadButton.Y, ActionBinding(
        ActionType.KEY, Keys.TAB, "Tab / Autocomplete"
    ))

    # Shoulder buttons
    profile.bind_button(GamepadButton.LB, ActionBinding(
        ActionType.KEY_COMBO, (Keys.SHIFT, Keys.TAB), "Shift+Tab"
    ))
    profile.bind_button(GamepadButton.RB, ActionBinding(
        ActionType.KEY, Keys.TAB, "Tab"
    ))

    # Start/Select
    profile.bind_button(GamepadButton.START, ActionBinding(
        ActionType.KEY_COMBO, (Keys.CONTROL, 'c'), "Ctrl+C (Interrupt)"
    ))
    profile.bind_button(GamepadButton.SELECT, ActionBinding(
        ActionType.KEY_COMBO, (Keys.CONTROL, 'd'), "Ctrl+D (EOF)"
    ))

    # D-pad for arrow keys
    profile.bind_dpad(DPadDirection.UP, ActionBinding(
        ActionType.KEY, Keys.UP, "Up arrow", repeat=True
    ))
    profile.bind_dpad(DPadDirection.DOWN, ActionBinding(
        ActionType.KEY, Keys.DOWN, "Down arrow", repeat=True
    ))
    profile.bind_dpad(DPadDirection.LEFT, ActionBinding(
        ActionType.KEY, Keys.LEFT, "Left arrow", repeat=True
    ))
    profile.bind_dpad(DPadDirection.RIGHT, ActionBinding(
        ActionType.KEY, Keys.RIGHT, "Right arrow", repeat=True
    ))

    # Left stick for arrow navigation with repeat
    profile.left_stick_up = ActionBinding(
        ActionType.KEY, Keys.UP, "Up arrow", repeat=True
    )
    profile.left_stick_down = ActionBinding(
        ActionType.KEY, Keys.DOWN, "Down arrow", repeat=True
    )
    profile.left_stick_left = ActionBinding(
        ActionType.KEY, Keys.LEFT, "Left arrow", repeat=True
    )
    profile.left_stick_right = ActionBinding(
        ActionType.KEY, Keys.RIGHT, "Right arrow", repeat=True
    )

    # Right stick for page navigation
    profile.right_stick_up = ActionBinding(
        ActionType.KEY, Keys.PAGE_UP, "Page Up"
    )
    profile.right_stick_down = ActionBinding(
        ActionType.KEY, Keys.PAGE_DOWN, "Page Down"
    )
    profile.right_stick_left = ActionBinding(
        ActionType.KEY, Keys.HOME, "Home"
    )
    profile.right_stick_right = ActionBinding(
        ActionType.KEY, Keys.END, "End"
    )

    return profile


def create_vim_profile() -> ControllerProfile:
    """Create a profile optimized for Vim/Neovim."""
    profile = ControllerProfile(
        name="Vim Mode",
        description="Vim-optimized controls"
    )

    # Face buttons - common Vim actions
    profile.bind_button(GamepadButton.A, ActionBinding(
        ActionType.KEY, Keys.ENTER, "Enter"
    ))
    profile.bind_button(GamepadButton.B, ActionBinding(
        ActionType.KEY, Keys.ESCAPE, "Escape (Normal mode)"
    ))
    profile.bind_button(GamepadButton.X, ActionBinding(
        ActionType.TEXT, 'x', "Delete character"
    ))
    profile.bind_button(GamepadButton.Y, ActionBinding(
        ActionType.TEXT, 'yy', "Yank line"
    ))

    # Shoulder buttons for undo/redo
    profile.bind_button(GamepadButton.LB, ActionBinding(
        ActionType.TEXT, 'u', "Undo"
    ))
    profile.bind_button(GamepadButton.RB, ActionBinding(
        ActionType.KEY_COMBO, (Keys.CONTROL, 'r'), "Redo"
    ))

    # Triggers for insert modes
    profile.left_trigger_binding = ActionBinding(
        ActionType.TEXT, 'i', "Insert mode"
    )
    profile.right_trigger_binding = ActionBinding(
        ActionType.TEXT, 'a', "Append mode"
    )

    # D-pad for hjkl navigation
    profile.bind_dpad(DPadDirection.UP, ActionBinding(
        ActionType.TEXT, 'k', "Move up", repeat=True
    ))
    profile.bind_dpad(DPadDirection.DOWN, ActionBinding(
        ActionType.TEXT, 'j', "Move down", repeat=True
    ))
    profile.bind_dpad(DPadDirection.LEFT, ActionBinding(
        ActionType.TEXT, 'h', "Move left", repeat=True
    ))
    profile.bind_dpad(DPadDirection.RIGHT, ActionBinding(
        ActionType.TEXT, 'l', "Move right", repeat=True
    ))

    # Left stick for word/paragraph movement
    profile.left_stick_up = ActionBinding(
        ActionType.TEXT, '{', "Previous paragraph"
    )
    profile.left_stick_down = ActionBinding(
        ActionType.TEXT, '}', "Next paragraph"
    )
    profile.left_stick_left = ActionBinding(
        ActionType.TEXT, 'b', "Previous word"
    )
    profile.left_stick_right = ActionBinding(
        ActionType.TEXT, 'w', "Next word"
    )

    # Right stick for file navigation
    profile.right_stick_up = ActionBinding(
        ActionType.TEXT, 'gg', "Go to top"
    )
    profile.right_stick_down = ActionBinding(
        ActionType.TEXT, 'G', "Go to bottom"
    )
    profile.right_stick_left = ActionBinding(
        ActionType.TEXT, '0', "Start of line"
    )
    profile.right_stick_right = ActionBinding(
        ActionType.TEXT, '$', "End of line"
    )

    return profile
