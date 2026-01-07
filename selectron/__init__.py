"""
Selectron - Electron App Automation via Selenium

A library for automating Electron-based applications using Selenium WebDriver.

Key Features:
    - Automatic Chrome version detection from Electron apps
    - ChromeDriver installation matching Electron's embedded Chrome
    - Session registry with persistence for recovery
    - Background process monitoring with auto-cleanup
    - External session discovery via port scanning
    - Port conflict resolution

Basic Usage:
    from selectron import ElectronDriverManager

    # Create manager for an app
    edm = ElectronDriverManager(app_name="Claude")

    # Start app with debugging
    session = edm.start_app_with_debugging(port=9222)

    # Create driver
    driver = edm.create_local_driver()

    # ... interact with the app ...

    # Clean up
    driver.quit()
    edm.stop_session()

Environment Variables:
    SELECTRON_DEFAULT_APP      - Default app name if not specified
    SELECTRON_DEFAULT_APP_DIR  - First directory to search for apps
    SELECTRON_SEARCH_DIRS      - Colon-separated list of additional directories

For more information, see the README.md or visit:
https://github.com/research-developer/Selectron
"""

__version__ = "0.2.0"
__author__ = "Preston"

# Core models
from .models import Session, SessionOrigin, SessionStatus, ElectronAppPaths

# Configuration
from .config import (
    SelectronConfig,
    get_config,
    set_config,
    reset_config,
    ENV_DEFAULT_APP,
    ENV_DEFAULT_APP_DIR,
    ENV_SEARCH_DIRS,
)

# Exceptions
from .exceptions import (
    SelectronError,
    PortConflictError,
    AppNotFoundError,
    ChromeVersionError,
    SessionNotFoundError,
    DriverInstallError,
    SessionStartError,
)

# Utilities
from .utils import (
    get_selenium_manager_path,
    is_port_in_use,
    find_available_port,
)

# Session Registry
from .registry import SessionRegistry, get_registry

# Process Monitor
from .monitor import ProcessMonitor, get_monitor

# Session Discovery
from .discovery import (
    SessionDiscovery,
    PortConflictHandler,
    get_devtools_info,
    get_devtools_targets,
)

# App Scanner
from .app_scanner import ElectronApp, AppRegistry, get_app_registry

# Main Driver Manager
from .driver import ElectronDriverManager

__all__ = [
    # Version
    "__version__",

    # Core models
    "Session",
    "SessionOrigin",
    "SessionStatus",
    "ElectronAppPaths",

    # Configuration
    "SelectronConfig",
    "get_config",
    "set_config",
    "reset_config",
    "ENV_DEFAULT_APP",
    "ENV_DEFAULT_APP_DIR",
    "ENV_SEARCH_DIRS",

    # Exceptions
    "SelectronError",
    "PortConflictError",
    "AppNotFoundError",
    "ChromeVersionError",
    "SessionNotFoundError",
    "DriverInstallError",
    "SessionStartError",

    # Utilities
    "get_selenium_manager_path",
    "is_port_in_use",
    "find_available_port",

    # Session Registry
    "SessionRegistry",
    "get_registry",

    # Process Monitor
    "ProcessMonitor",
    "get_monitor",

    # Session Discovery
    "SessionDiscovery",
    "PortConflictHandler",
    "get_devtools_info",
    "get_devtools_targets",

    # App Scanner
    "ElectronApp",
    "AppRegistry",
    "get_app_registry",

    # Main Driver Manager
    "ElectronDriverManager",
]
