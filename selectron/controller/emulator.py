"""
Software-driven game controller emulator.

Provides a mock gamepad that can be controlled programmatically,
useful for testing and development without physical hardware.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Dict, List, Optional, Tuple
from threading import Lock
import time


class GamepadButton(Enum):
    """Standard gamepad buttons (Xbox-style layout)."""
    # Face buttons
    A = auto()
    B = auto()
    X = auto()
    Y = auto()

    # Shoulder buttons
    LB = auto()  # Left bumper
    RB = auto()  # Right bumper
    LT = auto()  # Left trigger (digital)
    RT = auto()  # Right trigger (digital)

    # Stick clicks
    LS = auto()  # Left stick click
    RS = auto()  # Right stick click

    # Center buttons
    START = auto()
    SELECT = auto()  # Also called "Back" or "View"
    HOME = auto()    # Guide/Xbox button


class DPadDirection(Enum):
    """D-pad directions."""
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()

    # Diagonals
    UP_LEFT = auto()
    UP_RIGHT = auto()
    DOWN_LEFT = auto()
    DOWN_RIGHT = auto()

    # Neutral
    NONE = auto()


@dataclass
class StickState:
    """State of an analog stick."""
    x: float = 0.0  # -1.0 (left) to 1.0 (right)
    y: float = 0.0  # -1.0 (down) to 1.0 (up)

    @property
    def magnitude(self) -> float:
        """Get the magnitude of the stick deflection (0.0 to 1.0)."""
        import math
        return min(1.0, math.sqrt(self.x ** 2 + self.y ** 2))

    @property
    def angle(self) -> Optional[float]:
        """Get angle in degrees (0 = right, 90 = up), None if centered."""
        import math
        if self.magnitude < 0.1:  # Dead zone
            return None
        return math.degrees(math.atan2(self.y, self.x))


@dataclass
class TriggerState:
    """State of an analog trigger."""
    value: float = 0.0  # 0.0 (released) to 1.0 (fully pressed)

    @property
    def pressed(self) -> bool:
        """Check if trigger is pressed past threshold."""
        return self.value > 0.5


@dataclass
class GamepadState:
    """Complete state of a gamepad."""
    buttons: Dict[GamepadButton, bool] = field(default_factory=dict)
    dpad: DPadDirection = DPadDirection.NONE
    left_stick: StickState = field(default_factory=StickState)
    right_stick: StickState = field(default_factory=StickState)
    left_trigger: TriggerState = field(default_factory=TriggerState)
    right_trigger: TriggerState = field(default_factory=TriggerState)

    def __post_init__(self):
        # Initialize all buttons to False
        for button in GamepadButton:
            if button not in self.buttons:
                self.buttons[button] = False

    def is_pressed(self, button: GamepadButton) -> bool:
        """Check if a button is currently pressed."""
        return self.buttons.get(button, False)

    def get_pressed_buttons(self) -> List[GamepadButton]:
        """Get list of all currently pressed buttons."""
        return [b for b, pressed in self.buttons.items() if pressed]


# Callback type aliases
ButtonCallback = Callable[[GamepadButton, bool], None]  # (button, is_pressed)
DPadCallback = Callable[[DPadDirection], None]
StickCallback = Callable[[float, float], None]  # (x, y)
TriggerCallback = Callable[[float], None]  # (value)


class GamepadEmulator:
    """
    Software-driven gamepad emulator.

    Simulates a standard Xbox-style controller with:
    - Face buttons (A, B, X, Y)
    - Shoulder buttons (LB, RB) and triggers (LT, RT)
    - Two analog sticks with click
    - D-pad
    - Start, Select, Home buttons

    Example usage:
        gamepad = GamepadEmulator()

        # Register callbacks
        gamepad.on_button(lambda btn, pressed: print(f"{btn}: {pressed}"))
        gamepad.on_dpad(lambda dir: print(f"D-pad: {dir}"))

        # Simulate inputs
        gamepad.press(GamepadButton.A)
        gamepad.release(GamepadButton.A)
        gamepad.set_dpad(DPadDirection.UP)
        gamepad.move_left_stick(0.5, 0.0)
    """

    def __init__(self, name: str = "Emulated Gamepad"):
        self.name = name
        self._state = GamepadState()
        self._lock = Lock()

        # Callbacks
        self._button_callbacks: List[ButtonCallback] = []
        self._dpad_callbacks: List[DPadCallback] = []
        self._left_stick_callbacks: List[StickCallback] = []
        self._right_stick_callbacks: List[StickCallback] = []
        self._left_trigger_callbacks: List[TriggerCallback] = []
        self._right_trigger_callbacks: List[TriggerCallback] = []

        # Event history for debugging/replay
        self._event_history: List[Tuple[float, str, dict]] = []
        self._record_history = False

    @property
    def state(self) -> GamepadState:
        """Get current gamepad state (read-only copy)."""
        with self._lock:
            return GamepadState(
                buttons=dict(self._state.buttons),
                dpad=self._state.dpad,
                left_stick=StickState(self._state.left_stick.x, self._state.left_stick.y),
                right_stick=StickState(self._state.right_stick.x, self._state.right_stick.y),
                left_trigger=TriggerState(self._state.left_trigger.value),
                right_trigger=TriggerState(self._state.right_trigger.value),
            )

    # === Callback Registration ===

    def on_button(self, callback: ButtonCallback) -> None:
        """Register callback for button events."""
        self._button_callbacks.append(callback)

    def on_dpad(self, callback: DPadCallback) -> None:
        """Register callback for D-pad events."""
        self._dpad_callbacks.append(callback)

    def on_left_stick(self, callback: StickCallback) -> None:
        """Register callback for left stick movement."""
        self._left_stick_callbacks.append(callback)

    def on_right_stick(self, callback: StickCallback) -> None:
        """Register callback for right stick movement."""
        self._right_stick_callbacks.append(callback)

    def on_left_trigger(self, callback: TriggerCallback) -> None:
        """Register callback for left trigger changes."""
        self._left_trigger_callbacks.append(callback)

    def on_right_trigger(self, callback: TriggerCallback) -> None:
        """Register callback for right trigger changes."""
        self._right_trigger_callbacks.append(callback)

    # === Input Simulation ===

    def press(self, button: GamepadButton) -> None:
        """Press a button."""
        with self._lock:
            if not self._state.buttons.get(button, False):
                self._state.buttons[button] = True
                self._record_event('button_press', {'button': button.name})
                self._fire_button_callbacks(button, True)

    def release(self, button: GamepadButton) -> None:
        """Release a button."""
        with self._lock:
            if self._state.buttons.get(button, False):
                self._state.buttons[button] = False
                self._record_event('button_release', {'button': button.name})
                self._fire_button_callbacks(button, False)

    def tap(self, button: GamepadButton, duration: float = 0.1) -> None:
        """Press and release a button."""
        self.press(button)
        time.sleep(duration)
        self.release(button)

    def set_dpad(self, direction: DPadDirection) -> None:
        """Set D-pad direction."""
        with self._lock:
            if self._state.dpad != direction:
                self._state.dpad = direction
                self._record_event('dpad', {'direction': direction.name})
                self._fire_dpad_callbacks(direction)

    def move_left_stick(self, x: float, y: float) -> None:
        """Move the left stick (-1.0 to 1.0 for each axis)."""
        x = max(-1.0, min(1.0, x))
        y = max(-1.0, min(1.0, y))
        with self._lock:
            if self._state.left_stick.x != x or self._state.left_stick.y != y:
                self._state.left_stick.x = x
                self._state.left_stick.y = y
                self._record_event('left_stick', {'x': x, 'y': y})
                self._fire_left_stick_callbacks(x, y)

    def move_right_stick(self, x: float, y: float) -> None:
        """Move the right stick (-1.0 to 1.0 for each axis)."""
        x = max(-1.0, min(1.0, x))
        y = max(-1.0, min(1.0, y))
        with self._lock:
            if self._state.right_stick.x != x or self._state.right_stick.y != y:
                self._state.right_stick.x = x
                self._state.right_stick.y = y
                self._record_event('right_stick', {'x': x, 'y': y})
                self._fire_right_stick_callbacks(x, y)

    def set_left_trigger(self, value: float) -> None:
        """Set left trigger value (0.0 to 1.0)."""
        value = max(0.0, min(1.0, value))
        with self._lock:
            if self._state.left_trigger.value != value:
                self._state.left_trigger.value = value
                self._record_event('left_trigger', {'value': value})
                self._fire_left_trigger_callbacks(value)

    def set_right_trigger(self, value: float) -> None:
        """Set right trigger value (0.0 to 1.0)."""
        value = max(0.0, min(1.0, value))
        with self._lock:
            if self._state.right_trigger.value != value:
                self._state.right_trigger.value = value
                self._record_event('right_trigger', {'value': value})
                self._fire_right_trigger_callbacks(value)

    def reset(self) -> None:
        """Reset all inputs to neutral/released state."""
        with self._lock:
            for button in GamepadButton:
                if self._state.buttons.get(button, False):
                    self._state.buttons[button] = False
                    self._fire_button_callbacks(button, False)

            if self._state.dpad != DPadDirection.NONE:
                self._state.dpad = DPadDirection.NONE
                self._fire_dpad_callbacks(DPadDirection.NONE)

            if self._state.left_stick.x != 0 or self._state.left_stick.y != 0:
                self._state.left_stick.x = 0
                self._state.left_stick.y = 0
                self._fire_left_stick_callbacks(0, 0)

            if self._state.right_stick.x != 0 or self._state.right_stick.y != 0:
                self._state.right_stick.x = 0
                self._state.right_stick.y = 0
                self._fire_right_stick_callbacks(0, 0)

            if self._state.left_trigger.value != 0:
                self._state.left_trigger.value = 0
                self._fire_left_trigger_callbacks(0)

            if self._state.right_trigger.value != 0:
                self._state.right_trigger.value = 0
                self._fire_right_trigger_callbacks(0)

            self._record_event('reset', {})

    # === Combo/Sequence Support ===

    def combo(self, *buttons: GamepadButton, duration: float = 0.1) -> None:
        """Press multiple buttons simultaneously."""
        for button in buttons:
            self.press(button)
        time.sleep(duration)
        for button in buttons:
            self.release(button)

    def sequence(self, *inputs: Tuple, delay: float = 0.1) -> None:
        """
        Execute a sequence of inputs with delays.

        Each input is a tuple of (input_type, *args):
        - ('button', GamepadButton.A)
        - ('dpad', DPadDirection.UP)
        - ('left_stick', 0.5, 0.0)
        """
        for input_spec in inputs:
            input_type = input_spec[0]
            args = input_spec[1:]

            if input_type == 'button':
                self.tap(args[0])
            elif input_type == 'dpad':
                self.set_dpad(args[0])
            elif input_type == 'left_stick':
                self.move_left_stick(args[0], args[1])
            elif input_type == 'right_stick':
                self.move_right_stick(args[0], args[1])
            elif input_type == 'left_trigger':
                self.set_left_trigger(args[0])
            elif input_type == 'right_trigger':
                self.set_right_trigger(args[0])

            time.sleep(delay)

    # === Event History ===

    def start_recording(self) -> None:
        """Start recording events for playback/debugging."""
        self._record_history = True
        self._event_history.clear()

    def stop_recording(self) -> List[Tuple[float, str, dict]]:
        """Stop recording and return event history."""
        self._record_history = False
        return list(self._event_history)

    def _record_event(self, event_type: str, data: dict) -> None:
        """Record an event if recording is enabled."""
        if self._record_history:
            self._event_history.append((time.time(), event_type, data))

    # === Internal Callback Firing ===

    def _fire_button_callbacks(self, button: GamepadButton, pressed: bool) -> None:
        for callback in self._button_callbacks:
            try:
                callback(button, pressed)
            except Exception as e:
                print(f"Error in button callback: {e}")

    def _fire_dpad_callbacks(self, direction: DPadDirection) -> None:
        for callback in self._dpad_callbacks:
            try:
                callback(direction)
            except Exception as e:
                print(f"Error in D-pad callback: {e}")

    def _fire_left_stick_callbacks(self, x: float, y: float) -> None:
        for callback in self._left_stick_callbacks:
            try:
                callback(x, y)
            except Exception as e:
                print(f"Error in left stick callback: {e}")

    def _fire_right_stick_callbacks(self, x: float, y: float) -> None:
        for callback in self._right_stick_callbacks:
            try:
                callback(x, y)
            except Exception as e:
                print(f"Error in right stick callback: {e}")

    def _fire_left_trigger_callbacks(self, value: float) -> None:
        for callback in self._left_trigger_callbacks:
            try:
                callback(value)
            except Exception as e:
                print(f"Error in left trigger callback: {e}")

    def _fire_right_trigger_callbacks(self, value: float) -> None:
        for callback in self._right_trigger_callbacks:
            try:
                callback(value)
            except Exception as e:
                print(f"Error in right trigger callback: {e}")

    def __repr__(self) -> str:
        pressed = self.state.get_pressed_buttons()
        return f"GamepadEmulator(name={self.name!r}, pressed={[b.name for b in pressed]})"
