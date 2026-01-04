"""
Obsidian Page Object - JSON-Based POM

Thin wrapper around the JSON-defined elements and operations.
Provides type hints and additional convenience methods.

Usage:
    from poms.Obsidian.obsidian_page import ObsidianPage

    # With driver
    obsidian = ObsidianPage(driver)
    obsidian.open_quick_switcher()
    obsidian.search_in_switcher(text="My Note")
    obsidian.select_first_result()

    # iPython exploration
    from poms.Obsidian.obsidian_page import load_obsidian_elements
    elements = load_obsidian_elements()
    print(elements['quick_switcher'])
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


def load_obsidian_elements() -> dict:
    """
    Load Obsidian elements for inspection (no driver needed).

    Returns:
        Dictionary mapping element IDs to element definitions
    """
    with open(POM_DIR / 'elements.json', 'r') as f:
        data = json.load(f)
    return {elem['id']: elem for elem in data.get('elements', [])}


def load_obsidian_operations() -> dict:
    """
    Load Obsidian operations for inspection (no driver needed).

    Returns:
        Dictionary mapping operation names to operation definitions
    """
    with open(POM_DIR / 'operations.json', 'r') as f:
        data = json.load(f)
    return {op['name']: op for op in data.get('operations', [])}


class ObsidianPage(BasePOM):
    """
    Page Object for Obsidian note-taking application.

    Extends BasePOM with Obsidian-specific convenience methods.
    All operations from operations.json are available as methods.

    Example:
        obsidian = ObsidianPage(driver)

        # Navigate with quick switcher
        obsidian.open_quick_switcher()
        obsidian.search_note("My Note")
        obsidian.select_first_result()

        # Create content
        obsidian.create_new_note()
        obsidian.type_in_editor("# My Heading")
    """

    def __init__(self, driver: WebDriver, timeout: float = 10.0):
        """
        Initialize Obsidian Page Object.

        Args:
            driver: WebDriver instance connected to Obsidian
            timeout: Default wait timeout in seconds
        """
        pom_data = POMData('Obsidian', POM_DIR).load()
        super().__init__(driver, pom_data, timeout)

        # Switch to main Obsidian window
        self._switch_to_obsidian_window()

    def _switch_to_obsidian_window(self) -> None:
        """Switch to the main Obsidian window."""
        for handle in self._driver.window_handles:
            self._driver.switch_to.window(handle)
            if 'Obsidian' in self._driver.title:
                return
        if self._driver.window_handles:
            self._driver.switch_to.window(self._driver.window_handles[-1])

    # =========================================
    # Convenience Methods
    # =========================================

    def search_note(self, note_name: str, open_note: bool = True) -> None:
        """
        Search for and optionally open a note using quick switcher.

        Args:
            note_name: Name of the note to search for
            open_note: Whether to open the first result
        """
        self.open_quick_switcher()
        time.sleep(0.3)

        # Type in the switcher
        self.search_in_switcher(text=note_name)
        time.sleep(0.3)

        if open_note:
            self.select_first_result()
            time.sleep(0.3)

    def run_command(self, command_name: str) -> None:
        """
        Run a command by name using the command palette.

        Args:
            command_name: Name of the command to run
        """
        self.open_command_palette()
        time.sleep(0.3)

        # Type in palette
        try:
            input_el = self._driver.find_element(By.CSS_SELECTOR, '.prompt input')
            input_el.clear()
            input_el.send_keys(command_name)
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
        editor = self.find_element('editor')
        if editor:
            editor.click()
            ActionChains(self._driver).send_keys(text).perform()

    def get_open_tabs(self) -> List[str]:
        """
        Get list of open tab names.

        Returns:
            List of tab titles
        """
        tabs = self._driver.find_elements(By.CSS_SELECTOR, '.workspace-tab-header.tappable')
        return [tab.get_attribute('aria-label') or tab.text for tab in tabs]

    def get_active_tab(self) -> Optional[str]:
        """
        Get the name of the currently active tab.

        Returns:
            Active tab name or None
        """
        try:
            active = self._driver.find_element(
                By.CSS_SELECTOR, '.workspace-tab-header.is-active, .workspace-tab-header.mod-active'
            )
            return active.get_attribute('aria-label') or active.text
        except Exception:
            return None

    def switch_to_tab(self, tab_name: str) -> bool:
        """
        Switch to a tab by name.

        Args:
            tab_name: Name of the tab to switch to

        Returns:
            True if tab was found and clicked
        """
        tabs = self._driver.find_elements(By.CSS_SELECTOR, '.workspace-tab-header.tappable')
        for tab in tabs:
            label = tab.get_attribute('aria-label') or tab.text
            if label == tab_name:
                tab.click()
                return True
        return False

    def get_file_list(self) -> List[str]:
        """
        Get list of files in the file explorer.

        Returns:
            List of file names
        """
        files = self._driver.find_elements(By.CSS_SELECTOR, '.nav-file-title')
        return [f.text for f in files]

    def open_file(self, filename: str) -> bool:
        """
        Open a file from the file explorer.

        Args:
            filename: Name of the file to open

        Returns:
            True if file was found and clicked
        """
        files = self._driver.find_elements(By.CSS_SELECTOR, '.nav-file-title')
        for f in files:
            if f.text == filename:
                ActionChains(self._driver).double_click(f).perform()
                return True
        return False

    def is_modal_open(self) -> bool:
        """Check if any modal (like quick switcher) is open."""
        try:
            modal = self._driver.find_element(By.CSS_SELECTOR, '.prompt')
            return modal.is_displayed()
        except Exception:
            return False

    def get_ribbon_actions(self) -> List[str]:
        """
        Get list of available ribbon actions.

        Returns:
            List of ribbon action labels
        """
        actions = self._driver.find_elements(By.CSS_SELECTOR, '.side-dock-ribbon-action')
        return [a.get_attribute('aria-label') or '' for a in actions if a.get_attribute('aria-label')]

    def click_ribbon_action(self, label: str) -> bool:
        """
        Click a ribbon action by its label.

        Args:
            label: Aria-label of the ribbon action

        Returns:
            True if action was found and clicked
        """
        try:
            action = self._driver.find_element(By.CSS_SELECTOR, f'[aria-label="{label}"]')
            action.click()
            return True
        except Exception:
            return False


# Convenience function for quick loading
def load(driver: WebDriver, timeout: float = 10.0) -> ObsidianPage:
    """
    Quick loader for ObsidianPage.

    Usage:
        from poms.Obsidian import obsidian_page
        obsidian = obsidian_page.load(driver)
    """
    return ObsidianPage(driver, timeout)
