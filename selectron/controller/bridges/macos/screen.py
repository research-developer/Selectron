"""
macOS screen capture utilities.

Provides cursor position tracking and screen capture around the cursor
using Quartz/CoreGraphics and the native screencapture command.
"""

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, Optional
import os


@dataclass
class CaptureRegion:
    """Defines a rectangular screen region for capture."""
    x: int
    y: int
    width: int
    height: int

    def to_screencapture_arg(self) -> str:
        """Format as screencapture -R argument: x,y,w,h"""
        return f"{self.x},{self.y},{self.width},{self.height}"


def get_cursor_position() -> Tuple[int, int]:
    """
    Get current mouse cursor position.

    Returns:
        Tuple of (x, y) screen coordinates.
    """
    try:
        from Quartz import CGEventCreate, CGEventGetLocation
        event = CGEventCreate(None)
        point = CGEventGetLocation(event)
        return int(point.x), int(point.y)
    except ImportError:
        # Quartz is required for mouse position - no reliable fallback
        raise ImportError("pyobjc-framework-Quartz required: pip install pyobjc-framework-Quartz")


def get_screen_size() -> Tuple[int, int]:
    """
    Get the main screen dimensions.

    Returns:
        Tuple of (width, height).
    """
    try:
        from Quartz import CGDisplayBounds, CGMainDisplayID
        bounds = CGDisplayBounds(CGMainDisplayID())
        return int(bounds.size.width), int(bounds.size.height)
    except ImportError:
        # Fallback to reasonable defaults
        return 1920, 1080


def capture_region(
    region: CaptureRegion,
    output_path: Optional[str] = None,
) -> bytes:
    """
    Capture a rectangular region of the screen.

    Args:
        region: CaptureRegion defining the area to capture.
        output_path: Optional path to save the PNG. If None, uses temp file.

    Returns:
        PNG image data as bytes.
    """
    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix='.png')
        os.close(fd)
        cleanup = True
    else:
        cleanup = False

    try:
        # Use macOS screencapture command
        # -x: no sound
        # -R: capture specific region
        # -t png: output format
        subprocess.run(
            [
                'screencapture',
                '-x',  # No sound
                '-R', region.to_screencapture_arg(),
                '-t', 'png',
                output_path
            ],
            check=True,
            capture_output=True,
            timeout=5
        )

        return Path(output_path).read_bytes()

    finally:
        if cleanup and Path(output_path).exists():
            Path(output_path).unlink()


def capture_around_cursor(
    radius: int = 200,
    output_path: Optional[str] = None,
) -> bytes:
    """
    Capture a square region centered on the current cursor position.

    Args:
        radius: Half the width/height of capture region (default 200 = 400x400).
        output_path: Optional path to save the PNG.

    Returns:
        PNG image data as bytes.
    """
    x, y = get_cursor_position()
    screen_w, screen_h = get_screen_size()

    # Calculate region bounds, clamped to screen
    region = CaptureRegion(
        x=max(0, x - radius),
        y=max(0, y - radius),
        width=min(radius * 2, screen_w - max(0, x - radius)),
        height=min(radius * 2, screen_h - max(0, y - radius)),
    )

    return capture_region(region, output_path)


def capture_full_screen(output_path: Optional[str] = None) -> bytes:
    """
    Capture the entire main screen.

    Args:
        output_path: Optional path to save the PNG.

    Returns:
        PNG image data as bytes.
    """
    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix='.png')
        os.close(fd)
        cleanup = True
    else:
        cleanup = False

    try:
        subprocess.run(
            ['screencapture', '-x', '-t', 'png', output_path],
            check=True,
            capture_output=True,
            timeout=5
        )
        return Path(output_path).read_bytes()

    finally:
        if cleanup and Path(output_path).exists():
            Path(output_path).unlink()


# === Demo/Test ===

if __name__ == "__main__":
    print("Screen Capture Test")
    print("=" * 40)

    # Test cursor position
    x, y = get_cursor_position()
    print(f"Cursor position: ({x}, {y})")

    # Test screen size
    w, h = get_screen_size()
    print(f"Screen size: {w}x{h}")

    # Test capture around cursor
    print("\nCapturing 400x400 region around cursor...")
    data = capture_around_cursor(radius=200, output_path="/tmp/cursor_capture.png")
    print(f"Captured {len(data)} bytes -> /tmp/cursor_capture.png")

    print("\nDone! Check /tmp/cursor_capture.png")
