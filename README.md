# Selectron

**Electron App Automation via Selenium**

Selectron is a Python library for automating Electron-based applications (like Claude, Obsidian, VS Code, Slack, etc.) using Selenium WebDriver.

## The Problem

Electron apps embed a specific Chrome version. To automate them via Selenium, you need a ChromeDriver version that matches that embedded Chrome version exactly.

## The Solution

Selectron automatically:
1. **Detects** the Chrome version from the Electron app's framework binary
2. **Installs** the matching ChromeDriver via selenium-manager
3. **Manages** debugging sessions with a persistent registry
4. **Monitors** processes with auto-cleanup when they terminate

## Installation

```bash
pip install selenium  # Required dependency
# Then add selectron to your project
```

## Quick Start

```python
from selectron import ElectronDriverManager

# Create manager for an app
edm = ElectronDriverManager(app_name="Claude")

# Start app with remote debugging
session = edm.start_app_with_debugging(port=9222)

# Create a WebDriver connected to the app
driver = edm.create_local_driver()

# Interact with the app
print(driver.title)
print(driver.window_handles)

# Clean up
driver.quit()
edm.stop_session()
```

## Using Selenium Grid

If you're running a Selenium Grid server:

```bash
# Start Selenium server (with correct chromedriver version)
selenium-server standalone --port 4041 \
    --session-timeout 99999999 \
    --healthcheck-interval 99999999 \
    -I 'firefox' -I 'chrome'
```

```python
from selectron import ElectronDriverManager

edm = ElectronDriverManager(app_name="Obsidian")
session = edm.start_app_with_debugging()

# Connect via Selenium Grid
driver = edm.create_remote_driver(
    server_url="http://localhost:4041"
)
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SELECTRON_DEFAULT_APP` | Default app name if not specified |
| `SELECTRON_DEFAULT_APP_DIR` | First directory to search for apps |
| `SELECTRON_SEARCH_DIRS` | Colon-separated list of additional directories |

```bash
export SELECTRON_DEFAULT_APP=Claude
export SELECTRON_DEFAULT_APP_DIR=/Applications/MyApps
```

## App Registry

Scan your system for installed Electron apps:

```python
from selectron import get_app_registry

# Get the registry (loads from ~/.selectron/apps.json)
registry = get_app_registry()

# Scan for apps (first time or refresh)
registry.refresh()

# List all apps
for app in registry.all_apps():
    print(f"{app.name}: Chrome {app.chrome_version}")

# Lookup by name
claude = registry.get_by_name("Claude")
print(f"Claude uses Electron {claude.electron_version}")

# Search
for app in registry.search("Code"):
    print(app.name)
```

CLI usage:
```bash
# Scan and list all Electron apps
python -m selectron.app_scanner --refresh

# Search for apps
python -m selectron.app_scanner --search Cursor

# Get detailed info
python -m selectron.app_scanner --info Claude
```

## Session Discovery

Scan for externally-started debugging sessions:

```python
from selectron import scan_for_sessions, SessionDiscovery, get_registry

# Quick scan (returns list of dicts)
sessions = scan_for_sessions()
for s in sessions:
    print(f"Port {s['port']}: {s['browser']}")

# Registry-integrated discovery
discovery = SessionDiscovery(get_registry())
new_sessions = discovery.scan_and_register()
```

## Session Registry

Sessions are persisted to `~/.selectron/sessions.json` for recovery:

```python
from selectron import get_registry

registry = get_registry()

# List all sessions
for session in registry.all_sessions():
    print(f"{session.app_name} on port {session.port}: {session.status.value}")

# Find by port
session = registry.get_by_port(9222)

# Find by app name
claude_sessions = registry.get_by_app("Claude")
```

## Port Conflict Handling

When a port is already in use:

```python
from selectron import ElectronDriverManager

edm = ElectronDriverManager(app_name="Claude")

# Auto-find available port
session = edm.start_app_with_debugging(auto_find_port=True)

# Or handle conflicts manually
def my_conflict_handler(port, existing_session):
    print(f"Port {port} is in use!")
    return "cancel"  # or "add", "ignore", "kill"

session = edm.start_app_with_debugging(
    port=9222,
    on_conflict=my_conflict_handler
)
```

## API Reference

### ElectronDriverManager

Main interface for Electron app automation.

```python
ElectronDriverManager(
    app_name="AppName",           # Required (or set SELECTRON_DEFAULT_APP)
    app_dir=None,                 # Additional directory to search
    electron_binary_path=None,    # Explicit binary path
    electron_framework_path=None, # Explicit framework path
)
```

**Methods:**
- `get_chrome_version()` - Get embedded Chrome version
- `install(force=False)` - Install matching ChromeDriver
- `start_app_with_debugging(port=9222, ...)` - Start app with debugging
- `stop_session(session_id=None)` - Stop a session
- `detach_session(session_id=None)` - Stop monitoring without killing
- `create_local_driver(port=None)` - Create local WebDriver
- `create_remote_driver(server_url, port=None)` - Create remote WebDriver
- `scan_for_external_sessions()` - Discover external sessions

### Session

Represents an active debugging session.

```python
Session(
    session_id="uuid",
    port=9222,
    app_name="Claude",
    pid=12345,
    origin=SessionOrigin.OURS,   # or EXTERNAL
    status=SessionStatus.RUNNING, # RUNNING, TERMINATED, DETACHED, UNKNOWN
)
```

### Keyboard Shortcuts

```python
from selectron import send_shortcut
from selenium.webdriver.common.keys import Keys

# Send Cmd+J
send_shortcut(driver, 'j', Keys.COMMAND)

# Send Cmd+Shift+K
send_shortcut(driver, 'k', Keys.COMMAND, Keys.SHIFT)
```

## CLI Usage

```bash
# Show Chrome version
python electron_driver.py Claude --version-only

# Install matching ChromeDriver
python electron_driver.py Claude --install-only

# Start app and connect
python electron_driver.py Claude --start

# Use Selenium Grid
python electron_driver.py Claude --start --server http://localhost:4041

# Scan for active sessions
python electron_driver.py --scan

# List registered sessions
python electron_driver.py --list-sessions
```

## Roadmap

### v0.2.0 (Current)
- [x] Environment variable configuration (`SELECTRON_DEFAULT_APP`, etc.)
- [x] Case-insensitive app directory search with glob support
- [x] Session registry with file persistence
- [x] Background process monitoring with auto-cleanup
- [x] External session discovery via port scanning
- [x] Port conflict resolution (add/ignore/kill/cancel)

### v0.3.0 - Execution Logging
- [ ] Execution log format specification (JSON-Lines)
- [ ] Log rotation and compression
- [ ] Export to ML formats (Parquet)
- [ ] Embedding-based query for similar examples

### v0.4.0 - Service Mode
- [ ] Detached daemon implementation
- [ ] IPC via Unix sockets
- [ ] Parent process liveness monitoring
- [ ] User prompts on parent death (kill/attach/reattach/CLI)
- [ ] macOS Notification Center integration

### v0.5.0 - Multi-Platform
- [ ] Windows Electron app support
- [ ] Linux Electron app support
- [ ] Platform-specific path discovery

### v1.0.0 - Production Ready
- [ ] Comprehensive test suite
- [ ] PyPI package publication
- [ ] Documentation site

## Search Directories

By default, Selectron searches these directories for apps:

1. `SELECTRON_DEFAULT_APP_DIR` (if set)
2. `/Applications/`
3. `~/Applications/`
4. `/Applications/Setapp/`
5. `/Applications/*/` (subdirectories)

Directories are deduplicated case-insensitively (macOS is case-insensitive).

## License

MIT

## Contributing

Contributions welcome! Please open an issue or PR on GitHub.
