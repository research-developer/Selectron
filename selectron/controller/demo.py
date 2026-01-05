#!/usr/bin/env python3
"""
Interactive demo for the controller emulator.

Run with: python -m selectron.controller.demo

Keyboard mappings (simulating a gamepad):
    WASD    - Left stick
    IJKL    - Right stick
    Arrow   - D-pad
    Space   - A button
    B       - B button
    X       - X button
    Y       - Y button
    Q       - LB (left bumper)
    E       - RB (right bumper)
    1       - LT (left trigger)
    3       - RT (right trigger)
    Enter   - Start
    Tab     - Select
    R       - Reset all inputs
    P       - Print current state
    M       - Switch profile
    ESC     - Quit
"""

import sys
import time

from .core.emulator import GamepadEmulator, GamepadButton, DPadDirection
from .core.mapper import ControllerMapper, create_terminal_navigation_profile, create_vim_profile
from .core.executors import PrintExecutor
from .bridges.iterm.executor import AppleScriptExecutor


# ANSI escape codes for terminal UI
class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'

    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'


def clear_screen():
    print('\033[2J\033[H', end='')


def move_cursor(row: int, col: int):
    print(f'\033[{row};{col}H', end='')


def hide_cursor():
    print('\033[?25l', end='')


def show_cursor():
    print('\033[?25h', end='')


class ControllerDemo:
    """Interactive demo for testing the controller emulator."""

    def __init__(self, live_mode: bool = False):
        """
        Initialize the demo.

        Args:
            live_mode: If True, actually send keys to the frontmost app.
                      If False, just print what would be sent.
        """
        self.gamepad = GamepadEmulator("Demo Gamepad")
        self.mapper = ControllerMapper(self.gamepad)

        # Set up profiles
        self.profiles = [
            create_terminal_navigation_profile(),
            create_vim_profile(),
        ]
        self.current_profile_idx = 0

        # Set up executor
        if live_mode:
            try:
                self.executor = AppleScriptExecutor()
                print(f"{Colors.GREEN}Live mode enabled - keys will be sent to frontmost app{Colors.RESET}")
            except RuntimeError:
                print(f"{Colors.YELLOW}Live mode not available on this platform{Colors.RESET}")
                self.executor = PrintExecutor()
        else:
            self.executor = PrintExecutor()

        self.mapper.set_executor(self.executor.execute)
        self.mapper.load_profile(self.profiles[0])
        self.mapper.start()

        self._running = False
        self._last_action = ""
        self._action_time = 0

    def switch_profile(self):
        """Switch to the next profile."""
        self.current_profile_idx = (self.current_profile_idx + 1) % len(self.profiles)
        profile = self.profiles[self.current_profile_idx]
        self.mapper.load_profile(profile)
        self._last_action = f"Switched to: {profile.name}"
        self._action_time = time.time()

    def render_state(self):
        """Render the current gamepad state to the terminal."""
        state = self.gamepad.state

        # Build the display
        lines = []

        # Header
        profile = self.profiles[self.current_profile_idx]
        lines.append(f"{Colors.BOLD}=== Controller Demo ==={Colors.RESET}")
        lines.append(f"Profile: {Colors.CYAN}{profile.name}{Colors.RESET}")
        lines.append("")

        # Controller ASCII art with state
        pressed = state.get_pressed_buttons()
        pressed_names = {b.name for b in pressed}

        # Top row (bumpers/triggers)
        lt = f"{Colors.GREEN}[LT]{Colors.RESET}" if state.left_trigger.pressed else "[LT]"
        lb = f"{Colors.GREEN}[LB]{Colors.RESET}" if 'LB' in pressed_names else "[LB]"
        rb = f"{Colors.GREEN}[RB]{Colors.RESET}" if 'RB' in pressed_names else "[RB]"
        rt = f"{Colors.GREEN}[RT]{Colors.RESET}" if state.right_trigger.pressed else "[RT]"
        lines.append(f"  {lt} {lb}                    {rb} {rt}")

        # D-pad and face buttons row
        dpad = state.dpad
        d_up = f"{Colors.GREEN}U{Colors.RESET}" if dpad in (DPadDirection.UP, DPadDirection.UP_LEFT, DPadDirection.UP_RIGHT) else "."
        d_down = f"{Colors.GREEN}D{Colors.RESET}" if dpad in (DPadDirection.DOWN, DPadDirection.DOWN_LEFT, DPadDirection.DOWN_RIGHT) else "."
        d_left = f"{Colors.GREEN}L{Colors.RESET}" if dpad in (DPadDirection.LEFT, DPadDirection.UP_LEFT, DPadDirection.DOWN_LEFT) else "."
        d_right = f"{Colors.GREEN}R{Colors.RESET}" if dpad in (DPadDirection.RIGHT, DPadDirection.UP_RIGHT, DPadDirection.DOWN_RIGHT) else "."

        y_btn = f"{Colors.GREEN}Y{Colors.RESET}" if 'Y' in pressed_names else "Y"
        b_btn = f"{Colors.GREEN}B{Colors.RESET}" if 'B' in pressed_names else "B"
        a_btn = f"{Colors.GREEN}A{Colors.RESET}" if 'A' in pressed_names else "A"
        x_btn = f"{Colors.GREEN}X{Colors.RESET}" if 'X' in pressed_names else "X"

        lines.append(f"       {d_up}                        {y_btn}")
        lines.append(f"     {d_left} + {d_right}                    {x_btn}   {b_btn}")
        lines.append(f"       {d_down}                        {a_btn}")

        # Sticks row
        ls = state.left_stick
        rs = state.right_stick

        # Map stick position to a 5x5 grid position
        def stick_to_grid(x: float, y: float) -> tuple:
            gx = int((x + 1) / 2 * 4)
            gy = int((1 - (y + 1) / 2) * 4)
            return (gx, gy)

        ls_pos = stick_to_grid(ls.x, ls.y)
        rs_pos = stick_to_grid(rs.x, rs.y)

        lines.append("")
        lines.append("  Left Stick       Right Stick")

        # Draw 5x5 grids for sticks
        for row in range(5):
            left_row = ""
            right_row = ""
            for col in range(5):
                if (col, row) == ls_pos:
                    left_row += f"{Colors.GREEN}O{Colors.RESET}"
                elif row == 2 and col == 2:
                    left_row += "+"
                else:
                    left_row += "."

                if (col, row) == rs_pos:
                    right_row += f"{Colors.GREEN}O{Colors.RESET}"
                elif row == 2 and col == 2:
                    right_row += "+"
                else:
                    right_row += "."

            lines.append(f"    {left_row}            {right_row}")

        # Center buttons
        start = f"{Colors.GREEN}[START]{Colors.RESET}" if 'START' in pressed_names else "[START]"
        select = f"{Colors.GREEN}[SELECT]{Colors.RESET}" if 'SELECT' in pressed_names else "[SELECT]"
        lines.append("")
        lines.append(f"         {select}  {start}")

        # Separator
        lines.append("")
        lines.append("-" * 45)

        # Last action
        if self._last_action and time.time() - self._action_time < 2:
            lines.append(f"Last: {Colors.YELLOW}{self._last_action}{Colors.RESET}")
        else:
            lines.append("Last: -")

        # Instructions
        lines.append("")
        lines.append(f"{Colors.DIM}Keyboard: WASD/IJKL=sticks, Arrows=d-pad, Space=A{Colors.RESET}")
        lines.append(f"{Colors.DIM}B/X/Y=buttons, Q/E=bumpers, 1/3=triggers, M=profile{Colors.RESET}")
        lines.append(f"{Colors.DIM}R=reset, ESC=quit{Colors.RESET}")

        return lines

    def handle_keypress(self, key: str) -> bool:
        """
        Handle a keypress, returning False to quit.

        Returns:
            False if should quit, True otherwise.
        """
        key_lower = key.lower()

        # Quit
        if key == '\x1b':  # ESC
            return False

        # Reset
        if key_lower == 'r':
            self.gamepad.reset()
            self._last_action = "Reset all inputs"
            self._action_time = time.time()
            return True

        # Switch profile
        if key_lower == 'm':
            self.switch_profile()
            return True

        # Print state
        if key_lower == 'p':
            print(f"\n{self.gamepad.state}\n")
            return True

        # D-pad (arrow keys are escape sequences)
        if key == '\x1b[A':  # Up
            self.gamepad.set_dpad(DPadDirection.UP)
            time.sleep(0.1)
            self.gamepad.set_dpad(DPadDirection.NONE)
        elif key == '\x1b[B':  # Down
            self.gamepad.set_dpad(DPadDirection.DOWN)
            time.sleep(0.1)
            self.gamepad.set_dpad(DPadDirection.NONE)
        elif key == '\x1b[C':  # Right
            self.gamepad.set_dpad(DPadDirection.RIGHT)
            time.sleep(0.1)
            self.gamepad.set_dpad(DPadDirection.NONE)
        elif key == '\x1b[D':  # Left
            self.gamepad.set_dpad(DPadDirection.LEFT)
            time.sleep(0.1)
            self.gamepad.set_dpad(DPadDirection.NONE)

        # Face buttons
        elif key == ' ':  # Space = A
            self.gamepad.tap(GamepadButton.A)
        elif key_lower == 'b':
            self.gamepad.tap(GamepadButton.B)
        elif key_lower == 'x':
            self.gamepad.tap(GamepadButton.X)
        elif key_lower == 'y':
            self.gamepad.tap(GamepadButton.Y)

        # Shoulder buttons
        elif key_lower == 'q':
            self.gamepad.tap(GamepadButton.LB)
        elif key_lower == 'e':
            self.gamepad.tap(GamepadButton.RB)

        # Triggers
        elif key == '1':
            self.gamepad.set_left_trigger(1.0)
            time.sleep(0.1)
            self.gamepad.set_left_trigger(0.0)
        elif key == '3':
            self.gamepad.set_right_trigger(1.0)
            time.sleep(0.1)
            self.gamepad.set_right_trigger(0.0)

        # Start/Select
        elif key == '\r' or key == '\n':  # Enter = Start
            self.gamepad.tap(GamepadButton.START)
        elif key == '\t':  # Tab = Select
            self.gamepad.tap(GamepadButton.SELECT)

        # Left stick (WASD)
        elif key_lower == 'w':
            self.gamepad.move_left_stick(0, 1.0)
            time.sleep(0.1)
            self.gamepad.move_left_stick(0, 0)
        elif key_lower == 's':
            self.gamepad.move_left_stick(0, -1.0)
            time.sleep(0.1)
            self.gamepad.move_left_stick(0, 0)
        elif key_lower == 'a':
            self.gamepad.move_left_stick(-1.0, 0)
            time.sleep(0.1)
            self.gamepad.move_left_stick(0, 0)
        elif key_lower == 'd':
            self.gamepad.move_left_stick(1.0, 0)
            time.sleep(0.1)
            self.gamepad.move_left_stick(0, 0)

        # Right stick (IJKL)
        elif key_lower == 'i':
            self.gamepad.move_right_stick(0, 1.0)
            time.sleep(0.1)
            self.gamepad.move_right_stick(0, 0)
        elif key_lower == 'k':
            self.gamepad.move_right_stick(0, -1.0)
            time.sleep(0.1)
            self.gamepad.move_right_stick(0, 0)
        elif key_lower == 'j':
            self.gamepad.move_right_stick(-1.0, 0)
            time.sleep(0.1)
            self.gamepad.move_right_stick(0, 0)
        elif key_lower == 'l':
            self.gamepad.move_right_stick(1.0, 0)
            time.sleep(0.1)
            self.gamepad.move_right_stick(0, 0)

        return True

    def run(self):
        """Run the interactive demo."""
        import tty
        import termios
        import select

        # Save terminal settings
        old_settings = termios.tcgetattr(sys.stdin)

        try:
            # Set terminal to raw mode
            tty.setraw(sys.stdin.fileno())
            hide_cursor()

            self._running = True

            while self._running:
                # Render
                clear_screen()
                lines = self.render_state()
                for line in lines:
                    print(line + '\r')
                sys.stdout.flush()

                # Check for input (with timeout for refresh)
                rlist, _, _ = select.select([sys.stdin], [], [], 0.1)

                if rlist:
                    # Read character(s)
                    ch = sys.stdin.read(1)

                    # Handle escape sequences (arrow keys)
                    if ch == '\x1b':
                        # Read more characters if available
                        rlist2, _, _ = select.select([sys.stdin], [], [], 0.05)
                        if rlist2:
                            ch += sys.stdin.read(2)

                    if not self.handle_keypress(ch):
                        break

        finally:
            # Restore terminal
            show_cursor()
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
            print("\nDemo ended.")


def main():
    """Main entry point for the demo."""
    import argparse

    parser = argparse.ArgumentParser(description="Controller Emulator Demo")
    parser.add_argument(
        '--live', '-l',
        action='store_true',
        help='Enable live mode - actually send keys to frontmost app'
    )
    parser.add_argument(
        '--profile', '-p',
        choices=['terminal', 'vim'],
        default='terminal',
        help='Starting profile'
    )

    args = parser.parse_args()

    print(f"{Colors.BOLD}Controller Emulator Demo{Colors.RESET}")
    print()

    if args.live:
        print(f"{Colors.YELLOW}WARNING: Live mode enabled!{Colors.RESET}")
        print("Keys will be sent to the frontmost application.")
        print("Switch to another window to see the effect.")
        print()
        response = input("Continue? [y/N] ")
        if response.lower() != 'y':
            print("Aborted.")
            return

    demo = ControllerDemo(live_mode=args.live)

    # Set starting profile
    if args.profile == 'vim':
        demo.switch_profile()

    try:
        demo.run()
    except KeyboardInterrupt:
        # Allow clean exit on Ctrl+C without showing a stack trace.
        pass


if __name__ == '__main__':
    main()
