#!/usr/bin/env python3
"""
Hardware Gamepad Input - Real controller support.

Reads input from physical game controllers (Xbox, PlayStation, Luna, etc.)
and presents the same interface as GamepadEmulator for seamless integration.

Requires: pip install pygame
"""

import sys
import time
import threading
from dataclasses import dataclass
from typing import Callable, List, Optional

# macOS requires pygame event pump on main thread
IS_MACOS = sys.platform == "darwin"

from .emulator import (
    GamepadButton,
    DPadDirection,
    GamepadState,
    StickState,
    TriggerState,
)


# Standard SDL/Xbox button mapping
# These are the typical indices for Xbox-style controllers
class SDLButtonMap:
    """SDL GameController button indices (Xbox layout)."""
    A = 0
    B = 1
    X = 2
    Y = 3
    LB = 4  # Left Bumper
    RB = 5  # Right Bumper
    SELECT = 6  # Back/View
    START = 7  # Start/Menu
    HOME = 8  # Guide/Xbox button
    LS = 9  # Left stick click
    RS = 10  # Right stick click


class SDLAxisMap:
    """SDL GameController axis indices."""
    LEFT_X = 0
    LEFT_Y = 1
    RIGHT_X = 2
    RIGHT_Y = 3
    LT = 4  # Left Trigger (some controllers)
    RT = 5  # Right Trigger (some controllers)


class SDLHatMap:
    """SDL D-pad hat values."""
    CENTERED = 0
    UP = 1
    RIGHT = 2
    DOWN = 4
    LEFT = 8
    UP_RIGHT = UP | RIGHT  # 3
    DOWN_RIGHT = DOWN | RIGHT  # 6
    DOWN_LEFT = DOWN | LEFT  # 12
    UP_LEFT = UP | LEFT  # 9


# Map SDL hat values to our DPadDirection
HAT_TO_DPAD = {
    SDLHatMap.CENTERED: DPadDirection.NONE,
    SDLHatMap.UP: DPadDirection.UP,
    SDLHatMap.RIGHT: DPadDirection.RIGHT,
    SDLHatMap.DOWN: DPadDirection.DOWN,
    SDLHatMap.LEFT: DPadDirection.LEFT,
    SDLHatMap.UP_RIGHT: DPadDirection.UP_RIGHT,
    SDLHatMap.DOWN_RIGHT: DPadDirection.DOWN_RIGHT,
    SDLHatMap.DOWN_LEFT: DPadDirection.DOWN_LEFT,
    SDLHatMap.UP_LEFT: DPadDirection.UP_LEFT,
}

# Map SDL button indices to our GamepadButton
BUTTON_INDEX_MAP = {
    SDLButtonMap.A: GamepadButton.A,
    SDLButtonMap.B: GamepadButton.B,
    SDLButtonMap.X: GamepadButton.X,
    SDLButtonMap.Y: GamepadButton.Y,
    SDLButtonMap.LB: GamepadButton.LB,
    SDLButtonMap.RB: GamepadButton.RB,
    SDLButtonMap.SELECT: GamepadButton.SELECT,
    SDLButtonMap.START: GamepadButton.START,
    SDLButtonMap.HOME: GamepadButton.HOME,
    SDLButtonMap.LS: GamepadButton.LS,
    SDLButtonMap.RS: GamepadButton.RS,
}


@dataclass
class ControllerInfo:
    """Information about a connected controller."""
    index: int
    name: str
    guid: str
    num_buttons: int
    num_axes: int
    num_hats: int


class HardwareGamepad:
    """
    Hardware gamepad input reader.

    Reads from physical game controllers via pygame and presents
    the same interface as GamepadEmulator for seamless integration.

    Usage:
        gamepad = HardwareGamepad()
        gamepad.on_button(lambda btn, pressed: print(f"{btn}: {pressed}"))
        gamepad.start()

        # Or use with ControllerMapper:
        mapper = ControllerMapper(gamepad)
        mapper.load_profile(create_terminal_navigation_profile())
        mapper.start()
    """

    def __init__(
        self,
        controller_index: int = 0,
        deadzone: float = 0.15,
        trigger_threshold: float = 0.1,
        poll_rate: float = 0.016,  # ~60Hz
        use_threading: Optional[bool] = None,
    ):
        """
        Initialize the hardware gamepad reader.

        Args:
            controller_index: Which controller to use (0 = first)
            deadzone: Analog stick deadzone (0.0-1.0)
            trigger_threshold: Trigger activation threshold
            poll_rate: How often to poll for input (seconds)
            use_threading: Use background thread for polling. Defaults to True on
                          Linux/Windows, False on macOS (main thread required).
                          If False, call poll() manually from main thread.
        """
        self.controller_index = controller_index
        self.deadzone = deadzone
        self.trigger_threshold = trigger_threshold
        self.poll_rate = poll_rate
        # macOS requires event pump on main thread
        self.use_threading = use_threading if use_threading is not None else not IS_MACOS

        # State
        self._state = GamepadState()
        self._prev_state = GamepadState()
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Pygame objects
        self._pygame_initialized = False
        self._joystick = None
        self._controller_info: Optional[ControllerInfo] = None

        # Callbacks (same interface as GamepadEmulator)
        self._button_callbacks: List[Callable[[GamepadButton, bool], None]] = []
        self._dpad_callbacks: List[Callable[[DPadDirection], None]] = []
        self._stick_callbacks: List[Callable[[str, float, float], None]] = []
        self._trigger_callbacks: List[Callable[[str, float], None]] = []
        self._any_callbacks: List[Callable[[GamepadState], None]] = []

    @property
    def state(self) -> GamepadState:
        """Get current gamepad state."""
        with self._lock:
            return self._state

    @property
    def controller_info(self) -> Optional[ControllerInfo]:
        """Get info about the connected controller."""
        return self._controller_info

    @property
    def is_connected(self) -> bool:
        """Check if a controller is connected."""
        return self._joystick is not None

    # === Callback Registration (same as GamepadEmulator) ===

    def on_button(self, callback: Callable[[GamepadButton, bool], None]) -> None:
        """Register callback for button events."""
        self._button_callbacks.append(callback)

    def on_dpad(self, callback: Callable[[DPadDirection], None]) -> None:
        """Register callback for D-pad events."""
        self._dpad_callbacks.append(callback)

    def on_stick(self, callback: Callable[[str, float, float], None]) -> None:
        """Register callback for stick movement."""
        self._stick_callbacks.append(callback)

    def on_trigger(self, callback: Callable[[str, float], None]) -> None:
        """Register callback for trigger changes."""
        self._trigger_callbacks.append(callback)

    def on_any(self, callback: Callable[[GamepadState], None]) -> None:
        """Register callback for any state change."""
        self._any_callbacks.append(callback)

    # === Controller Management ===

    @staticmethod
    def list_controllers() -> List[ControllerInfo]:
        """
        List all connected controllers.

        Returns:
            List of ControllerInfo for each connected controller
        """
        try:
            import pygame
        except ImportError:
            raise ImportError("pygame is required: pip install pygame")

        if not pygame.get_init():
            pygame.init()
        if not pygame.joystick.get_init():
            pygame.joystick.init()

        controllers = []
        for i in range(pygame.joystick.get_count()):
            joy = pygame.joystick.Joystick(i)
            joy.init()
            controllers.append(ControllerInfo(
                index=i,
                name=joy.get_name(),
                guid=joy.get_guid() if hasattr(joy, 'get_guid') else "unknown",
                num_buttons=joy.get_numbuttons(),
                num_axes=joy.get_numaxes(),
                num_hats=joy.get_numhats(),
            ))

        return controllers

    def _init_pygame(self) -> bool:
        """Initialize pygame and connect to controller."""
        try:
            import pygame
        except ImportError:
            raise ImportError("pygame is required: pip install pygame")

        if not pygame.get_init():
            pygame.init()
        if not pygame.joystick.get_init():
            pygame.joystick.init()

        self._pygame_initialized = True

        # Check for controllers
        count = pygame.joystick.get_count()
        if count == 0:
            print("No controllers detected")
            return False

        if self.controller_index >= count:
            print(f"Controller {self.controller_index} not found (only {count} connected)")
            return False

        # Initialize the joystick
        self._joystick = pygame.joystick.Joystick(self.controller_index)
        self._joystick.init()

        self._controller_info = ControllerInfo(
            index=self.controller_index,
            name=self._joystick.get_name(),
            guid=self._joystick.get_guid() if hasattr(self._joystick, 'get_guid') else "unknown",
            num_buttons=self._joystick.get_numbuttons(),
            num_axes=self._joystick.get_numaxes(),
            num_hats=self._joystick.get_numhats(),
        )

        print(f"Connected to: {self._controller_info.name}")
        print(f"  Buttons: {self._controller_info.num_buttons}")
        print(f"  Axes: {self._controller_info.num_axes}")
        print(f"  Hats: {self._controller_info.num_hats}")

        return True

    def start(self) -> bool:
        """
        Start reading from the controller.

        On macOS, this initializes pygame but does NOT start a background thread.
        You must call poll() from your main loop. On other platforms, a background
        thread handles polling automatically.

        Returns:
            True if started successfully, False otherwise
        """
        if self._running:
            return True

        if not self._init_pygame():
            return False

        self._running = True

        if self.use_threading:
            self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
            self._poll_thread.start()
        # On macOS (non-threaded), user must call poll() manually

        return True

    def stop(self) -> None:
        """Stop reading from the controller."""
        self._running = False
        if self._poll_thread:
            self._poll_thread.join(timeout=1.0)
            self._poll_thread = None

    def poll(self) -> None:
        """
        Poll controller once (for main-thread usage on macOS).

        Call this from your main loop when use_threading=False.
        On platforms using threading, this is a no-op.
        """
        if not self._running or not self._joystick:
            return
        if self.use_threading:
            return  # Background thread handles it

        import pygame
        pygame.event.pump()
        self._read_state()
        self._process_changes()

    def _poll_loop(self) -> None:
        """Main polling loop - runs in background thread."""
        import pygame

        while self._running:
            # Process pygame events
            pygame.event.pump()

            # Read current state
            self._read_state()

            # Check for changes and fire callbacks
            self._process_changes()

            # Sleep for poll rate
            time.sleep(self.poll_rate)

    def _apply_deadzone(self, value: float) -> float:
        """Apply deadzone to an axis value."""
        if abs(value) < self.deadzone:
            return 0.0
        # Scale the remaining range to 0-1
        sign = 1 if value > 0 else -1
        return sign * (abs(value) - self.deadzone) / (1.0 - self.deadzone)

    def _read_state(self) -> None:
        """Read current state from the controller."""
        if not self._joystick:
            return

        with self._lock:
            # Store previous state
            self._prev_state = GamepadState(
                buttons=self._state.buttons.copy(),
                dpad=self._state.dpad,
                left_stick=StickState(self._state.left_stick.x, self._state.left_stick.y),
                right_stick=StickState(self._state.right_stick.x, self._state.right_stick.y),
                left_trigger=TriggerState(self._state.left_trigger.value),
                right_trigger=TriggerState(self._state.right_trigger.value),
            )

            # Read buttons
            for sdl_idx, our_button in BUTTON_INDEX_MAP.items():
                if sdl_idx < self._joystick.get_numbuttons():
                    pressed = self._joystick.get_button(sdl_idx)
                    self._state.buttons[our_button] = bool(pressed)

            # Read D-pad (hat)
            if self._joystick.get_numhats() > 0:
                hat = self._joystick.get_hat(0)
                # Convert tuple to bitmask
                hat_value = 0
                if hat[1] > 0:  # Up
                    hat_value |= SDLHatMap.UP
                elif hat[1] < 0:  # Down
                    hat_value |= SDLHatMap.DOWN
                if hat[0] > 0:  # Right
                    hat_value |= SDLHatMap.RIGHT
                elif hat[0] < 0:  # Left
                    hat_value |= SDLHatMap.LEFT

                self._state.dpad = HAT_TO_DPAD.get(hat_value, DPadDirection.NONE)

            # Read analog sticks
            if self._joystick.get_numaxes() >= 2:
                lx = self._apply_deadzone(self._joystick.get_axis(SDLAxisMap.LEFT_X))
                ly = self._apply_deadzone(-self._joystick.get_axis(SDLAxisMap.LEFT_Y))  # Invert Y
                self._state.left_stick = StickState(lx, ly)

            if self._joystick.get_numaxes() >= 4:
                rx = self._apply_deadzone(self._joystick.get_axis(SDLAxisMap.RIGHT_X))
                ry = self._apply_deadzone(-self._joystick.get_axis(SDLAxisMap.RIGHT_Y))  # Invert Y
                self._state.right_stick = StickState(rx, ry)

            # Read triggers
            # Some controllers have triggers as axes 4/5, others as buttons
            if self._joystick.get_numaxes() >= 6:
                # Triggers as axes (normalize from -1..1 to 0..1)
                lt = (self._joystick.get_axis(SDLAxisMap.LT) + 1) / 2
                rt = (self._joystick.get_axis(SDLAxisMap.RT) + 1) / 2
                self._state.left_trigger = TriggerState(lt)
                self._state.right_trigger = TriggerState(rt)

    def _process_changes(self) -> None:
        """Compare states and fire callbacks for changes."""
        state = self._state
        prev = self._prev_state
        changed = False

        # Check buttons
        for button in GamepadButton:
            curr = state.buttons.get(button, False)
            prev_val = prev.buttons.get(button, False)
            if curr != prev_val:
                changed = True
                for cb in self._button_callbacks:
                    try:
                        cb(button, curr)
                    except Exception as e:
                        print(f"Button callback error: {e}")

        # Check D-pad
        if state.dpad != prev.dpad:
            changed = True
            for cb in self._dpad_callbacks:
                try:
                    cb(state.dpad)
                except Exception as e:
                    print(f"D-pad callback error: {e}")

        # Check sticks (with some tolerance)
        if (abs(state.left_stick.x - prev.left_stick.x) > 0.01 or
            abs(state.left_stick.y - prev.left_stick.y) > 0.01):
            changed = True
            for cb in self._stick_callbacks:
                try:
                    cb("left", state.left_stick.x, state.left_stick.y)
                except Exception as e:
                    print(f"Stick callback error: {e}")

        if (abs(state.right_stick.x - prev.right_stick.x) > 0.01 or
            abs(state.right_stick.y - prev.right_stick.y) > 0.01):
            changed = True
            for cb in self._stick_callbacks:
                try:
                    cb("right", state.right_stick.x, state.right_stick.y)
                except Exception as e:
                    print(f"Stick callback error: {e}")

        # Check triggers
        if abs(state.left_trigger.value - prev.left_trigger.value) > 0.01:
            changed = True
            for cb in self._trigger_callbacks:
                try:
                    cb("left", state.left_trigger.value)
                except Exception as e:
                    print(f"Trigger callback error: {e}")

        if abs(state.right_trigger.value - prev.right_trigger.value) > 0.01:
            changed = True
            for cb in self._trigger_callbacks:
                try:
                    cb("right", state.right_trigger.value)
                except Exception as e:
                    print(f"Trigger callback error: {e}")

        # Fire any-change callbacks
        if changed:
            for cb in self._any_callbacks:
                try:
                    cb(state)
                except Exception as e:
                    print(f"Any callback error: {e}")


def list_controllers() -> List[ControllerInfo]:
    """List all connected game controllers."""
    return HardwareGamepad.list_controllers()


def create_hardware_gamepad(
    controller_index: int = 0,
    deadzone: float = 0.15,
) -> HardwareGamepad:
    """
    Create and initialize a hardware gamepad.

    Args:
        controller_index: Which controller to use (0 = first)
        deadzone: Analog stick deadzone

    Returns:
        Configured HardwareGamepad instance
    """
    return HardwareGamepad(
        controller_index=controller_index,
        deadzone=deadzone,
    )


# === Demo / Test ===

def demo():
    """Interactive demo to test hardware gamepad input."""
    print("Hardware Gamepad Demo")
    print("=" * 40)
    print()

    # List controllers
    controllers = list_controllers()
    if not controllers:
        print("No controllers found!")
        print("Make sure your controller is connected and recognized by the OS.")
        return

    print(f"Found {len(controllers)} controller(s):")
    for c in controllers:
        print(f"  [{c.index}] {c.name}")
    print()

    # Create gamepad (will auto-detect macOS and disable threading)
    gamepad = HardwareGamepad()

    if IS_MACOS:
        print("(macOS detected - using main thread polling)")
        print()

    # Register callbacks
    def on_button(button: GamepadButton, pressed: bool):
        action = "PRESSED" if pressed else "released"
        print(f"Button {button.name}: {action}")

    def on_dpad(direction: DPadDirection):
        if direction != DPadDirection.NONE:
            print(f"D-pad: {direction.name}")

    def on_stick(stick: str, x: float, y: float):
        if abs(x) > 0.1 or abs(y) > 0.1:
            print(f"{stick.title()} Stick: ({x:.2f}, {y:.2f})")

    def on_trigger(trigger: str, value: float):
        if value > 0.1:
            print(f"{trigger.title()} Trigger: {value:.2f}")

    gamepad.on_button(on_button)
    gamepad.on_dpad(on_dpad)
    gamepad.on_stick(on_stick)
    gamepad.on_trigger(on_trigger)

    # Start
    if not gamepad.start():
        print("Failed to start gamepad!")
        return

    print()
    print("Press buttons on your controller to test...")
    print("Press Ctrl+C to exit")
    print()

    try:
        while True:
            # On macOS, we need to poll manually from main thread
            if not gamepad.use_threading:
                gamepad.poll()
            time.sleep(gamepad.poll_rate)
    except KeyboardInterrupt:
        pass

    gamepad.stop()
    print("\nDemo ended.")


if __name__ == "__main__":
    demo()
