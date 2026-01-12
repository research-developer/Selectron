"""
macOS-specific utilities for screen capture and cursor management.
"""

from .screen import (
    CaptureRegion,
    get_cursor_position,
    capture_around_cursor,
    capture_region,
)

__all__ = [
    "CaptureRegion",
    "get_cursor_position",
    "capture_around_cursor",
    "capture_region",
]
