"""
Selectron Utilities

Shared utility functions for the Selectron library.
"""

import platform
import socket
from pathlib import Path


def get_selenium_manager_path() -> Path:
    """
    Get the path to selenium-manager bundled with the selenium package.

    Returns:
        Path to the selenium-manager executable

    Raises:
        RuntimeError: If the platform is not supported
        FileNotFoundError: If selenium-manager is not found
    """
    import selenium
    selenium_dir = Path(selenium.__file__).parent

    system = platform.system().lower()
    if system == "darwin":
        sm_path = selenium_dir / "webdriver" / "common" / "macos" / "selenium-manager"
    elif system == "linux":
        sm_path = selenium_dir / "webdriver" / "common" / "linux" / "selenium-manager"
    elif system == "windows":
        sm_path = selenium_dir / "webdriver" / "common" / "windows" / "selenium-manager.exe"
    else:
        raise RuntimeError(f"Unsupported platform: {system}")

    if not sm_path.exists():
        raise FileNotFoundError(f"selenium-manager not found at {sm_path}")

    return sm_path


def is_port_in_use(port: int, host: str = "localhost") -> bool:
    """
    Check if a port is currently in use.

    Args:
        port: Port number to check
        host: Host to check (default: localhost)

    Returns:
        True if the port is in use, False otherwise
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def find_available_port(start_port: int = 9222, max_attempts: int = 100) -> int:
    """
    Find an available port starting from start_port.

    Args:
        start_port: Port to start searching from
        max_attempts: Maximum number of ports to try

    Returns:
        First available port found

    Raises:
        RuntimeError: If no available port is found within max_attempts
    """
    for port in range(start_port, start_port + max_attempts):
        if not is_port_in_use(port):
            return port
    raise RuntimeError(
        f"No available port found in range {start_port}-{start_port + max_attempts - 1}"
    )
