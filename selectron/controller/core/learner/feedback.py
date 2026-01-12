"""
Visual and audio feedback for the learning system.

Provides screen flashing, cursor modification, and sound playback
to indicate learning states (recording, attempting, success, failure).
"""

import subprocess
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Optional


class FeedbackType(Enum):
    """Types of visual/audio feedback."""
    LEARNING = "learning"      # Purple pulse - recording demonstration
    ATTEMPTING = "attempting"  # Yellow flash - trying learned action
    SUCCESS = "success"        # Green flash - action completed
    FAILED = "failed"          # Red flash - action failed
    RELEARN = "relearn"        # Blue flash - entering re-learn mode


# ANSI color codes for terminal feedback (fallback)
COLORS = {
    FeedbackType.LEARNING: "\033[95m",    # Purple/Magenta
    FeedbackType.ATTEMPTING: "\033[93m",  # Yellow
    FeedbackType.SUCCESS: "\033[92m",     # Green
    FeedbackType.FAILED: "\033[91m",      # Red
    FeedbackType.RELEARN: "\033[94m",     # Blue
}
RESET = "\033[0m"

# macOS color names for AppleScript
APPLESCRIPT_COLORS = {
    FeedbackType.LEARNING: "{50000, 0, 50000}",    # Purple
    FeedbackType.ATTEMPTING: "{65535, 55000, 0}",  # Yellow
    FeedbackType.SUCCESS: "{0, 55000, 0}",         # Green
    FeedbackType.FAILED: "{55000, 0, 0}",          # Red
    FeedbackType.RELEARN: "{0, 30000, 60000}",     # Blue
}


def play_sound(sound_path: Path, pitch_shift: float = 1.0) -> None:
    """
    Play a notification sound.

    Args:
        sound_path: Path to .wav or .aiff file.
        pitch_shift: Speed/pitch multiplier (>1 = higher, <1 = lower).
    """
    if not sound_path.exists():
        print(f"Sound file not found: {sound_path}")
        return

    try:
        if pitch_shift != 1.0:
            # Use ffplay with tempo filter for pitch shift
            subprocess.Popen(
                [
                    'ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet',
                    '-af', f'atempo={pitch_shift}',
                    str(sound_path)
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            # Use native afplay for normal playback
            subprocess.Popen(
                ['afplay', str(sound_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
    except FileNotFoundError:
        # ffplay not installed, fall back to afplay
        subprocess.Popen(
            ['afplay', str(sound_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )


def flash_screen_applescript(color_rgb: str, duration: float = 0.3) -> None:
    """
    Flash the screen with a color overlay using AppleScript.

    Creates a temporary full-screen window with the specified color,
    then closes it after the duration.

    Args:
        color_rgb: AppleScript RGB color string like "{65535, 0, 0}".
        duration: How long to show the flash in seconds.
    """
    script = f'''
    tell application "System Events"
        set screenBounds to bounds of first item of (screens)
        set screenWidth to item 3 of screenBounds
        set screenHeight to item 4 of screenBounds
    end tell

    -- Create a brief visual flash using Finder window
    tell application "Finder"
        activate
        delay {duration}
        -- Flash is just the window activation effect
    end tell
    '''
    # Note: Full color overlay requires more complex implementation
    # For now, we use a simpler approach with terminal colors
    try:
        subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            timeout=duration + 1
        )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        pass


def flash_screen_terminal(feedback_type: FeedbackType, duration: float = 0.3) -> None:
    """
    Flash the terminal with a colored background.

    Uses ANSI escape codes to briefly change the terminal background.
    This is a simple fallback when screen overlay isn't available.

    Args:
        feedback_type: Type of feedback to display.
        duration: How long to show the flash.
    """
    color = COLORS.get(feedback_type, COLORS[FeedbackType.LEARNING])

    # Set background color
    bg_color = color.replace('[9', '[10')  # Convert foreground to background code

    # Flash
    print(f"\033[2J{bg_color}", end='', flush=True)  # Clear and set bg
    time.sleep(duration)
    print(f"\033[0m\033[2J", end='', flush=True)  # Reset and clear


class LearningFeedback:
    """
    Manages visual and audio feedback for the learning system.

    Coordinates screen flashing, sound playback, and terminal output
    to provide clear feedback during learning operations.
    """

    def __init__(
        self,
        sound_path: Optional[Path] = None,
        use_screen_flash: bool = True,
        use_terminal_flash: bool = True,
        use_sound: bool = True,
    ):
        """
        Initialize the feedback system.

        Args:
            sound_path: Path to notification sound file.
            use_screen_flash: Enable screen color overlay.
            use_terminal_flash: Enable terminal color flash.
            use_sound: Enable sound playback.
        """
        self.sound_path = sound_path
        self.use_screen_flash = use_screen_flash
        self.use_terminal_flash = use_terminal_flash
        self.use_sound = use_sound

        # State for pulsing/looping
        self._learning_active = False
        self._pulse_thread: Optional[threading.Thread] = None

    def flash(
        self,
        feedback_type: FeedbackType,
        duration: float = 0.3,
    ) -> None:
        """
        Trigger a single flash for the given feedback type.

        Args:
            feedback_type: Type of feedback.
            duration: Flash duration in seconds.
        """
        # Play sound based on feedback type
        if self.use_sound and self.sound_path:
            pitch = {
                FeedbackType.LEARNING: 1.0,
                FeedbackType.ATTEMPTING: 1.0,
                FeedbackType.SUCCESS: 1.3,   # Higher pitch
                FeedbackType.FAILED: 0.7,    # Lower pitch
                FeedbackType.RELEARN: 1.0,
            }.get(feedback_type, 1.0)

            play_sound(self.sound_path, pitch_shift=pitch)

            # Double-play for relearn
            if feedback_type == FeedbackType.RELEARN:
                threading.Timer(0.3, lambda: play_sound(self.sound_path)).start()

        # Visual flash
        if self.use_terminal_flash:
            flash_screen_terminal(feedback_type, duration)

        # Log to console
        color = COLORS.get(feedback_type, "")
        print(f"{color}[{feedback_type.name}]{RESET}")

    def start_learning(self) -> None:
        """
        Start learning mode with pulsing feedback.

        Plays looping sound and pulses the screen until stop_learning is called.
        """
        if self._learning_active:
            return

        self._learning_active = True

        # Play initial sound
        if self.use_sound and self.sound_path:
            play_sound(self.sound_path)

        # Start pulse thread
        def pulse_loop():
            while self._learning_active:
                if self.use_terminal_flash:
                    color = COLORS[FeedbackType.LEARNING]
                    print(f"{color}[RECORDING...]{RESET}", end='\r', flush=True)
                time.sleep(0.5)
                if self._learning_active:
                    print(" " * 20, end='\r', flush=True)
                    time.sleep(0.5)

        self._pulse_thread = threading.Thread(target=pulse_loop, daemon=True)
        self._pulse_thread.start()

        print(f"{COLORS[FeedbackType.LEARNING]}[LEARNING MODE STARTED]{RESET}")

    def stop_learning(self, success: bool = True) -> None:
        """
        Stop learning mode and show result.

        Args:
            success: Whether learning completed successfully.
        """
        self._learning_active = False

        if self._pulse_thread:
            self._pulse_thread.join(timeout=1.0)
            self._pulse_thread = None

        # Clear the pulsing line
        print(" " * 30, end='\r', flush=True)

        # Show result
        if success:
            self.flash(FeedbackType.SUCCESS)
            print(f"{COLORS[FeedbackType.SUCCESS]}[LEARNING COMPLETE]{RESET}")
        else:
            self.flash(FeedbackType.FAILED)
            print(f"{COLORS[FeedbackType.FAILED]}[LEARNING FAILED]{RESET}")

    @property
    def is_learning(self) -> bool:
        """Check if currently in learning mode."""
        return self._learning_active


# === Demo ===

if __name__ == "__main__":
    print("Feedback System Test")
    print("=" * 40)

    # Find notification sound
    sound_path = Path(__file__).parents[4] / "assets" / "notification.wav"
    if not sound_path.exists():
        sound_path = None
        print("Note: notification.wav not found, testing without sound")

    feedback = LearningFeedback(sound_path=sound_path)

    print("\nTesting flash types:")
    for ftype in FeedbackType:
        print(f"\n{ftype.name}:")
        feedback.flash(ftype, duration=0.5)
        time.sleep(0.8)

    print("\n\nTesting learning mode (3 seconds):")
    feedback.start_learning()
    time.sleep(3)
    feedback.stop_learning(success=True)

    print("\nDone!")
