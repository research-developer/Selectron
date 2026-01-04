"""
Selectron CLI

Command-line interface for automating Electron applications.

Usage:
    selectron claude --send "Hello Claude!"
    selectron claude --send "What's up?" --port 9222

Environment Variables:
    SELECTRON_CLAUDE_PORT - Default debugging port (default: 9222)
    SELECTRON_CLAUDE_SESSION_ID - Default session ID to use
"""

import os
import sys
import time
import click
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from .driver import ElectronDriverManager


# Environment variable names
ENV_CLAUDE_PORT = "SELECTRON_CLAUDE_PORT"
ENV_CLAUDE_SESSION_ID = "SELECTRON_CLAUDE_SESSION_ID"


def get_default_port() -> int:
    """Get default port from environment or use 9222."""
    return int(os.environ.get(ENV_CLAUDE_PORT, "9222"))


def get_default_session_id() -> Optional[str]:
    """Get default session ID from environment."""
    return os.environ.get(ENV_CLAUDE_SESSION_ID)


@click.group()
@click.version_option()
def cli():
    """Selectron - Electron App Automation via Selenium"""
    pass


@cli.group()
def claude():
    """Interact with Claude desktop app."""
    pass


@claude.command("send")
@click.argument("message")
@click.option(
    "--port", "-p",
    type=int,
    default=None,
    help=f"Debugging port (default: {get_default_port()}, env: {ENV_CLAUDE_PORT})"
)
@click.option(
    "--session-id", "-s",
    type=str,
    default=None,
    help=f"Session ID to use (env: {ENV_CLAUDE_SESSION_ID})"
)
@click.option(
    "--wait/--no-wait", "-w",
    default=True,
    help="Wait for response (default: True)"
)
@click.option(
    "--timeout", "-t",
    type=int,
    default=120,
    help="Response timeout in seconds (default: 120)"
)
@click.option(
    "--new-chat", "-n",
    is_flag=True,
    default=False,
    help="Start a new chat before sending"
)
def send_message(
    message: str,
    port: Optional[int],
    session_id: Optional[str],
    wait: bool,
    timeout: int,
    new_chat: bool
):
    """Send a message to Claude.

    Examples:
        selectron claude send "Hello Claude!"
        selectron claude send "What's up?" --port 9222
        selectron claude send "New topic" --new-chat
    """
    # Resolve port and session_id from args or env
    port = port or get_default_port()
    session_id = session_id or get_default_session_id()

    click.echo(f"Connecting to Claude on port {port}...")

    try:
        # Create driver manager and connect
        edm = ElectronDriverManager(app_name="Claude")
        driver = edm.create_local_driver(debugging_port=port)

        # Switch to Claude window
        for handle in driver.window_handles:
            driver.switch_to.window(handle)
            if driver.title == "Claude":
                break

        click.echo(f"Connected to: {driver.title}")

        # Start new chat if requested
        if new_chat:
            from selenium.webdriver.common.keys import Keys
            from .driver import send_shortcut
            send_shortcut(driver, 'n', Keys.COMMAND)
            time.sleep(1.5)
            click.echo("Started new chat")

        # 1. Click container to focus the editor
        container = driver.find_element(
            By.CSS_SELECTOR,
            '[data-testid="chat-input-grid-container"]'
        )
        driver.execute_script('arguments[0].click();', container)
        time.sleep(0.3)

        # 2. Type message using ActionChains (triggers React events)
        ActionChains(driver).send_keys(message).perform()
        click.echo(f"Typed: {message[:50]}{'...' if len(message) > 50 else ''}")

        # 3. Click the send button
        send_btn = driver.find_element(
            By.CSS_SELECTOR,
            'button[aria-label*="Send"]'
        )
        send_btn.click()
        click.echo("Message sent!")

        # Wait for response if requested
        if wait:
            click.echo(f"Waiting for response (timeout: {timeout}s)...")

            # Wait for streaming to complete by polling
            start_time = time.time()
            last_text = ""

            while time.time() - start_time < timeout:
                time.sleep(2)

                # Check if stop button exists (still streaming)
                stop_buttons = driver.find_elements(
                    By.CSS_SELECTOR,
                    '[data-testid="stop-button"], button[aria-label*="Stop"]'
                )
                if not stop_buttons:
                    # No stop button = done streaming
                    time.sleep(1)
                    break

                # Show progress
                current_text = driver.find_element(By.TAG_NAME, 'body').text
                if current_text != last_text:
                    click.echo(".", nl=False)
                    last_text = current_text

            click.echo("")  # newline after dots

            # Get the response
            try:
                body_text = driver.find_element(By.TAG_NAME, 'body').text

                # Extract just the last part (response area)
                if message in body_text:
                    parts = body_text.split(message)
                    if len(parts) > 1:
                        response = parts[-1].strip()
                        # Clean up footer text
                        for marker in ["Opus", "Sonnet", "Haiku", "Claude is AI"]:
                            if marker in response:
                                response = response.split(marker)[0].strip()
                        if response:
                            click.echo("\n--- Claude's Response ---")
                            click.echo(response)
                        else:
                            click.echo("Response received (unable to extract text)")
                else:
                    click.echo("Response received")

            except Exception as e:
                click.echo(f"Error reading response: {e}", err=True)

        # Don't quit the driver - leave Claude running
        # driver.quit()

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@claude.command("status")
@click.option(
    "--port", "-p",
    type=int,
    default=None,
    help=f"Debugging port to check (default: {get_default_port()})"
)
def check_status(port: Optional[int]):
    """Check if Claude is running with debugging enabled."""
    from .discovery import get_devtools_info

    port = port or get_default_port()

    click.echo(f"Checking port {port}...")

    info = get_devtools_info(port)
    if info:
        click.echo(f"Claude is running!")
        click.echo(f"  Browser: {info.get('Browser', 'Unknown')}")
        click.echo(f"  WebKit: {info.get('WebKit-Version', 'Unknown')}")
    else:
        click.echo(f"No debugging session found on port {port}")
        click.echo("\nTo start Claude with debugging:")
        click.echo(f"  /Applications/Claude.app/Contents/MacOS/Claude --remote-debugging-port={port}")


@claude.command("list")
def list_sessions():
    """List active Claude debugging sessions."""
    from .discovery import scan_for_sessions

    click.echo("Scanning for active sessions...")
    sessions = scan_for_sessions(port_range=(9222, 9250))

    if not sessions:
        click.echo("No active sessions found")
        return

    click.echo(f"\nFound {len(sessions)} session(s):\n")
    for session in sessions:
        click.echo(f"  Port {session['port']}: {session.get('Browser', 'Unknown')}")


@cli.command("scan")
@click.option(
    "--refresh", "-r",
    is_flag=True,
    help="Refresh the app registry"
)
def scan_apps(refresh: bool):
    """Scan for installed Electron apps."""
    from .app_scanner import get_app_registry

    registry = get_app_registry()

    if refresh or not registry.apps:
        click.echo("Scanning for Electron apps...")
        from .app_scanner import scan_all_directories
        apps = scan_all_directories()
        click.echo(f"Found {len(apps)} Electron apps")

    if registry.apps:
        click.echo(f"\nRegistered Electron apps ({len(registry.apps)}):\n")
        for name in sorted(registry.apps.keys())[:20]:
            app = registry.apps[name]
            click.echo(f"  {name}: Chrome {app.chrome_version}")
        if len(registry.apps) > 20:
            click.echo(f"  ... and {len(registry.apps) - 20} more")


@cli.command("discover")
@click.argument("app_name")
@click.option(
    "--port", "-p",
    type=int,
    default=None,
    help="Debugging port (default: 9222)"
)
@click.option(
    "--output", "-o",
    type=click.Path(),
    default=None,
    help="Output directory for POM files (default: ./poms)"
)
@click.option(
    "--screenshot/--no-screenshot",
    default=True,
    help="Take a screenshot (default: True)"
)
@click.option(
    "--include-hidden",
    is_flag=True,
    default=False,
    help="Include hidden elements in scan"
)
def discover_app(
    app_name: str,
    port: Optional[int],
    output: Optional[str],
    screenshot: bool,
    include_hidden: bool
):
    """
    Discover and classify UI elements in an Electron app.

    Takes a screenshot, scans all interactive elements, classifies them
    by CRUD operation type using SLTT, and generates a Page Object Model.

    Examples:
        selectron discover Claude
        selectron discover Obsidian --port 9223
        selectron discover Cursor --output ./my_poms
    """
    import json
    from pathlib import Path
    from datetime import datetime

    # Import webber's bridge
    try:
        # Webber uses 'from src.*' imports, so we need the webber root in path
        webber_root = '/Users/preston/research-developer/webber'
        if webber_root not in sys.path:
            sys.path.insert(0, webber_root)
        from src.integration.selectron_bridge import SelectronBridge, POMGenerator
    except ImportError as e:
        click.echo(f"Error: Could not import SelectronBridge: {e}", err=True)
        click.echo(f"Details: {e}")
        click.echo("Make sure webber is available at /Users/preston/research-developer/webber")
        sys.exit(1)

    port = port or get_default_port()
    output_dir = Path(output) if output else Path("./poms")
    output_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"Discovering UI elements in {app_name} on port {port}...")

    try:
        # Connect to the app
        edm = ElectronDriverManager(app_name=app_name)
        driver = edm.create_local_driver(debugging_port=port)

        # Switch to main window
        main_title = None
        for handle in driver.window_handles:
            driver.switch_to.window(handle)
            if app_name.lower() in driver.title.lower():
                main_title = driver.title
                break

        if not main_title:
            driver.switch_to.window(driver.window_handles[-1])
            main_title = driver.title

        click.echo(f"Connected to: {main_title}")

        # Take screenshot
        if screenshot:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = output_dir / f"{app_name}_{timestamp}.png"
            driver.save_screenshot(str(screenshot_path))
            click.echo(f"Screenshot saved: {screenshot_path}")

        # Scan and classify elements
        click.echo("Scanning interactive elements...")
        bridge = SelectronBridge()
        elements = bridge.scan_and_classify(
            driver,
            include_hidden=include_hidden
        )

        click.echo(f"Found {len(elements)} interactive elements")

        # Show classification summary
        by_crud = {}
        for elem in elements:
            op = elem.crud_operation.value
            if op not in by_crud:
                by_crud[op] = []
            by_crud[op].append(elem)

        click.echo("\nClassification Summary:")
        for op, elems in sorted(by_crud.items()):
            click.echo(f"  {op.upper()}: {len(elems)} elements")

        # Generate legacy POM (for reference)
        click.echo("\nGenerating Page Object Model...")
        generator = POMGenerator()
        class_name = f"{app_name.replace(' ', '')}Page"
        pom_code = generator.generate(elements, class_name=class_name)

        # Create app-specific directory
        app_dir = output_dir / app_name.replace(' ', '')
        app_dir.mkdir(parents=True, exist_ok=True)

        # Convert elements to new format and count by CRUD type
        by_crud_counts = {}
        element_defs = []

        for elem in elements:
            op = elem.crud_operation.value
            by_crud_counts[op] = by_crud_counts.get(op, 0) + 1

            # Create element definition
            elem_dict = elem.to_dict()
            selector_type = "css"
            selector_value = ""

            # Determine best selector
            if elem_dict.get('aria_label'):
                selector_type = "aria_label"
                selector_value = elem_dict['aria_label']
            elif elem_dict.get('id'):
                selector_type = "id"
                selector_value = elem_dict['id']
            elif elem_dict.get('css_selector'):
                selector_type = "css"
                selector_value = elem_dict['css_selector']
            elif elem_dict.get('xpath'):
                selector_type = "xpath"
                selector_value = elem_dict['xpath']

            # Generate unique ID
            method_name = elem_dict.get('suggested_method_name', '')
            elem_id = method_name.replace('_to_', '_').replace('create_', '').replace('read_', '').replace('update_', '').replace('delete_', '').replace('navigate_', '')
            if not elem_id:
                elem_id = f"element_{len(elements_data['elements'])}"

            element_def = {
                "id": elem_id,
                "selector": {"type": selector_type, "value": selector_value},
                "crud_type": elem_dict.get('crud_operation', 'unknown'),
                "component_type": elem_dict.get('component_type', 'Element'),
                "confidence": elem_dict.get('confidence', 0.5)
            }
            if elem_dict.get('aria_label') and selector_type != 'aria_label':
                element_def["aria_label"] = elem_dict['aria_label']

            element_defs.append(element_def)

        # Create elements.json structure
        elements_data = {
            "app_name": app_name,
            "version": "1.0.0",
            "generated_at": datetime.now().isoformat(),
            "description": f"{app_name} application",
            "default_timeout": 10.0,
            "element_count": len(elements),
            "by_operation": by_crud_counts,
            "elements": element_defs
        }

        elements_path = app_dir / "elements.json"
        elements_path.write_text(json.dumps(elements_data, indent=2))
        click.echo(f"Elements saved: {elements_path}")

        # Generate operations.json from elements
        operations_data = {
            "app_name": app_name,
            "version": "1.0.0",
            "operations": []
        }

        # Create operations from CRUD-classified elements
        for elem_def in elements_data['elements']:
            crud_type = elem_def['crud_type']
            op_name = elem_def['id']

            # Add CRUD prefix if not already present
            if crud_type == 'create' and not op_name.startswith('create_'):
                op_name = f"create_{op_name}"
            elif crud_type == 'navigate' and not op_name.startswith(('navigate_', 'open_', 'go_')):
                op_name = f"open_{op_name}"

            operation = {
                "name": op_name,
                "element_id": elem_def['id'],
                "action": "click",
                "description": f"{crud_type.title()}: {elem_def.get('aria_label', elem_def['id'])}"
            }
            operations_data['operations'].append(operation)

        operations_path = app_dir / "operations.json"
        operations_path.write_text(json.dumps(operations_data, indent=2))
        click.echo(f"Operations saved: {operations_path}")

        # Generate thin wrapper class
        wrapper_code = f'''"""
{app_name} Page Object - JSON-Based POM

Auto-generated by selectron discover command.
Provides type hints and convenience methods.

Usage:
    from poms.{app_name.replace(' ', '')}.{app_name.lower().replace(' ', '_')}_page import {class_name}

    # With driver
    page = {class_name}(driver)

    # iPython exploration
    from poms.{app_name.replace(' ', '')}.{app_name.lower().replace(' ', '_')}_page import load_{app_name.lower().replace(' ', '_')}_elements
    elements = load_{app_name.lower().replace(' ', '_')}_elements()
"""

from pathlib import Path
from typing import Optional, List
import json

from selenium.webdriver.remote.webdriver import WebDriver

try:
    from selectron.pom_loader import POMLoader, BasePOM, POMData
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from selectron.pom_loader import POMLoader, BasePOM, POMData


POM_DIR = Path(__file__).parent


def load_{app_name.lower().replace(' ', '_')}_elements() -> dict:
    """Load {app_name} elements for inspection (no driver needed)."""
    with open(POM_DIR / 'elements.json', 'r') as f:
        data = json.load(f)
    return {{elem['id']: elem for elem in data.get('elements', [])}}


def load_{app_name.lower().replace(' ', '_')}_operations() -> dict:
    """Load {app_name} operations for inspection (no driver needed)."""
    with open(POM_DIR / 'operations.json', 'r') as f:
        data = json.load(f)
    return {{op['name']: op for op in data.get('operations', [])}}


class {class_name}(BasePOM):
    """
    Page Object for {app_name}.

    Auto-generated. Add convenience methods as needed.
    """

    def __init__(self, driver: WebDriver, timeout: float = 10.0):
        pom_data = POMData('{app_name}', POM_DIR).load()
        super().__init__(driver, pom_data, timeout)


def load(driver: WebDriver, timeout: float = 10.0) -> {class_name}:
    """Quick loader for {class_name}."""
    return {class_name}(driver, timeout)
'''

        wrapper_path = app_dir / f"{app_name.lower().replace(' ', '_')}_page.py"
        wrapper_path.write_text(wrapper_code)
        click.echo(f"Wrapper saved: {wrapper_path}")

        # Also save legacy POM for backwards compatibility
        pom_path = app_dir / f"{app_name.lower().replace(' ', '_')}_page_legacy.py"
        pom_path.write_text(pom_code)
        click.echo(f"Legacy POM saved: {pom_path}")

        click.echo(f"\nDiscovery complete! Files saved to {app_dir}/")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
