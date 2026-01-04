"""
Cursor Page Object - JSON-Based POM

Thin wrapper around the JSON-defined elements and operations.
Provides type hints and additional convenience methods.

Usage:
    from poms.Cursor.cursor_page import CursorPage

    # With driver
    cursor = CursorPage(driver)
    cursor.open_command_palette()
    cursor.create_new_chat()
    cursor.toggle_ai_pane()

    # iPython exploration
    from poms.Cursor.cursor_page import load_cursor_elements
    elements = load_cursor_elements()
    print(elements['new_chat_btn'])
"""

from pathlib import Path
from typing import Optional, List, Any
import json
import time

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Import the loader
try:
    from selectron.pom_loader import POMLoader, BasePOM, POMData
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from selectron.pom_loader import POMLoader, BasePOM, POMData


# Path to this POM's directory
POM_DIR = Path(__file__).parent


def load_cursor_elements() -> dict:
    """
    Load Cursor elements for inspection (no driver needed).

    Returns:
        Dictionary mapping element IDs to element definitions
    """
    with open(POM_DIR / 'elements.json', 'r') as f:
        data = json.load(f)
    return {elem['id']: elem for elem in data.get('elements', [])}


def load_cursor_operations() -> dict:
    """
    Load Cursor operations for inspection (no driver needed).

    Returns:
        Dictionary mapping operation names to operation definitions
    """
    with open(POM_DIR / 'operations.json', 'r') as f:
        data = json.load(f)
    return {op['name']: op for op in data.get('operations', [])}


class CursorPage(BasePOM):
    """
    Page Object for Cursor AI-powered IDE.

    Extends BasePOM with Cursor-specific convenience methods.
    All operations from operations.json are available as methods.

    Example:
        cursor = CursorPage(driver)

        # Use AI features
        cursor.toggle_ai_pane()
        cursor.create_new_chat()

        # Navigation
        cursor.open_command_palette()
        cursor.open_quick_open()

        # Editor
        cursor.save_file()
        cursor.find_in_file()
    """

    def __init__(self, driver: WebDriver, timeout: float = 10.0):
        """
        Initialize Cursor Page Object.

        Args:
            driver: WebDriver instance connected to Cursor
            timeout: Default wait timeout in seconds
        """
        pom_data = POMData('Cursor', POM_DIR).load()
        super().__init__(driver, pom_data, timeout)

        # Switch to main Cursor window
        self._switch_to_cursor_window()

    def _switch_to_cursor_window(self) -> None:
        """Switch to the main Cursor window."""
        for handle in self._driver.window_handles:
            self._driver.switch_to.window(handle)
            if 'Cursor' in self._driver.title or '.py' in self._driver.title or '.ts' in self._driver.title:
                return
        if self._driver.window_handles:
            self._driver.switch_to.window(self._driver.window_handles[-1])

    # =========================================
    # Convenience Methods
    # =========================================

    def run_command(self, command_name: str) -> None:
        """
        Run a command by name using the command palette.

        Args:
            command_name: Name of the command to run
        """
        self.open_command_palette()
        time.sleep(0.3)

        # Type in the command palette
        try:
            input_el = self._driver.find_element(By.CSS_SELECTOR, '.quick-input-widget input')
            input_el.clear()
            input_el.send_keys(command_name)
            time.sleep(0.3)
            input_el.send_keys(Keys.ENTER)
        except Exception:
            pass

    def open_file(self, filename: str) -> None:
        """
        Open a file using quick open.

        Args:
            filename: Name or path of the file to open
        """
        self.open_quick_open()
        time.sleep(0.3)

        try:
            input_el = self._driver.find_element(By.CSS_SELECTOR, '.quick-input-widget input')
            input_el.clear()
            input_el.send_keys(filename)
            time.sleep(0.3)
            input_el.send_keys(Keys.ENTER)
        except Exception:
            pass

    def type_in_editor(self, text: str) -> None:
        """
        Type text into the active editor.

        Args:
            text: Text to type
        """
        editor = self.find_element('editor_textarea')
        if editor:
            editor.click()
            ActionChains(self._driver).send_keys(text).perform()

    def get_active_tab_name(self) -> Optional[str]:
        """
        Get the name of the currently active editor tab.

        Returns:
            Active tab name or None
        """
        try:
            active_tab = self.find_element('editor_tab_active')
            if active_tab:
                return active_tab.get_attribute('aria-label')
        except Exception:
            pass
        return None

    def get_open_tabs(self) -> List[str]:
        """
        Get list of open editor tabs.

        Returns:
            List of tab names
        """
        tabs = self._driver.find_elements(By.CSS_SELECTOR, '.tab[role="tab"]')
        return [tab.get_attribute('aria-label') or tab.text for tab in tabs]

    def get_errors_count(self) -> int:
        """
        Get the number of errors shown in the status bar.

        Returns:
            Number of errors
        """
        try:
            errors_el = self.find_element('errors_warnings')
            if errors_el:
                # Parse "Errors: X, Warnings: Y" format
                label = errors_el.get_attribute('aria-label') or ''
                if 'Errors:' in label:
                    parts = label.split(',')
                    for part in parts:
                        if 'Errors:' in part:
                            return int(part.split(':')[1].strip())
        except Exception:
            pass
        return 0

    def get_warnings_count(self) -> int:
        """
        Get the number of warnings shown in the status bar.

        Returns:
            Number of warnings
        """
        try:
            errors_el = self.find_element('errors_warnings')
            if errors_el:
                label = errors_el.get_attribute('aria-label') or ''
                if 'Warnings:' in label:
                    parts = label.split(',')
                    for part in parts:
                        if 'Warnings:' in part:
                            return int(part.split(':')[1].strip())
        except Exception:
            pass
        return 0

    def get_workspace_name(self) -> Optional[str]:
        """
        Get the current workspace name.

        Returns:
            Workspace name or None
        """
        try:
            workspace_el = self.find_element('workspace_indicator')
            if workspace_el:
                label = workspace_el.get_attribute('aria-label') or ''
                if 'Workspace:' in label:
                    return label.replace('Workspace:', '').strip()
        except Exception:
            pass
        return None

    def is_ai_pane_visible(self) -> bool:
        """Check if the AI pane is currently visible."""
        try:
            ai_toggle = self.find_element('toggle_ai_pane')
            if ai_toggle:
                classes = ai_toggle.get_attribute('class') or ''
                return 'checked' in classes
        except Exception:
            pass
        return False

    def is_terminal_visible(self) -> bool:
        """Check if the terminal panel is visible."""
        try:
            terminal_section = self.find_element('terminal_section')
            return terminal_section is not None and terminal_section.is_displayed()
        except Exception:
            return False

    def get_file_list(self) -> List[str]:
        """
        Get list of files visible in the explorer.

        Returns:
            List of file names
        """
        files = self._driver.find_elements(By.CSS_SELECTOR, '.monaco-list-row[role="treeitem"]')
        return [f.get_attribute('aria-label') or f.text for f in files if f.text]

    def click_file(self, filename: str) -> bool:
        """
        Click a file in the explorer by name.

        Args:
            filename: Name of the file to click

        Returns:
            True if file was found and clicked
        """
        files = self._driver.find_elements(By.CSS_SELECTOR, '.monaco-list-row[role="treeitem"]')
        for f in files:
            label = f.get_attribute('aria-label') or f.text
            if label == filename or filename in label:
                f.click()
                return True
        return False

    def send_chat_message(self, message: str) -> None:
        """
        Send a message in the AI chat.

        Args:
            message: Message to send
        """
        # Ensure AI pane is visible
        if not self.is_ai_pane_visible():
            self.toggle_ai_pane()
            time.sleep(0.3)

        # Find composer and type
        composer = self.find_element('composer_bar')
        if composer:
            composer.click()
            ActionChains(self._driver).send_keys(message).perform()
            ActionChains(self._driver).send_keys(Keys.ENTER).perform()


# Convenience function for quick loading
def load(driver: WebDriver, timeout: float = 10.0) -> CursorPage:
    """
    Quick loader for CursorPage.

    Usage:
        from poms.Cursor import cursor_page
        cursor = cursor_page.load(driver)
    """
    return CursorPage(driver, timeout)
