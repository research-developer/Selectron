"""
Cursor IDE Page Object Model

Provides a high-level interface for automating the Cursor AI code editor
using W3C WebDriver/WebElement component patterns.

Cursor is based on VS Code/Monaco, so many patterns are similar.
Generated from SLTT classifier scan with 98 elements classified.
"""

import platform
import re
from typing import Optional, List
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException

# Cross-platform modifier key
MODIFIER_KEY = Keys.COMMAND if platform.system() == 'Darwin' else Keys.CONTROL

from ..components import (
    BasePage,
    BaseComponent,
    TextInputComponent,
    ButtonComponent,
    LinkComponent,
    TabsComponent,
    ComponentWait,
)


# ============================================================================
# Cursor-Specific Component Classes
# ============================================================================

class EditorTabComponent(BaseComponent):
    """
    Cursor's editor tab for open files.

    Similar to VS Code's tab system.
    """

    @property
    def filename(self) -> str:
        """Get the filename shown in the tab."""
        return self.get_attribute('aria-label') or self.text.strip()

    @property
    def is_active(self) -> bool:
        """Check if this tab is currently active."""
        classes = self.get_attribute('class') or ''
        return 'active' in classes and 'selected' in classes

    @property
    def is_dirty(self) -> bool:
        """Check if the file has unsaved changes."""
        classes = self.get_attribute('class') or ''
        return 'dirty' in classes

    def activate(self) -> None:
        """Click to switch to this tab."""
        self.click()

    def close(self) -> None:
        """Close this tab."""
        try:
            close_btn = self.find_child(By.CSS_SELECTOR, '[aria-label*="Close"]')
            close_btn.click()
        except NoSuchElementException:
            # Fallback: use keyboard shortcut to close the active tab
            ActionChains(self.driver).key_down(MODIFIER_KEY).send_keys('w').key_up(MODIFIER_KEY).perform()


class FileExplorerComponent(BaseComponent):
    """
    Cursor's File Explorer panel.

    Shows the project's file structure in a tree view.
    """

    @property
    def files(self) -> List[BaseComponent]:
        """Get all visible file items in the tree."""
        file_elements = self.find_children(By.CSS_SELECTOR, '[role="treeitem"]')
        return [BaseComponent(el) for el in file_elements]

    def get_file(self, name: str) -> Optional[BaseComponent]:
        """Get a file by name."""
        for file in self.files:
            if file.get_attribute('aria-label') == name or file.text == name:
                return file
        return None

    def open_file(self, name: str) -> bool:
        """Open a file by name (double-click)."""
        file = self.get_file(name)
        if file:
            ActionChains(self.driver).double_click(file._root).perform()
            return True
        return False


class TerminalComponent(BaseComponent):
    """
    Cursor's integrated terminal panel.
    """

    def send_command(self, command: str) -> None:
        """Send a command to the terminal."""
        self.click()
        ActionChains(self.driver).send_keys(command).send_keys(Keys.ENTER).perform()

    def clear(self) -> None:
        """Clear the terminal."""
        self.click()
        ActionChains(self.driver).key_down(MODIFIER_KEY).send_keys('k').key_up(MODIFIER_KEY).perform()


class AIChatComponent(BaseComponent):
    """
    Cursor's AI Chat pane.

    Provides AI-assisted code generation and chat.
    """

    @property
    def is_visible(self) -> bool:
        """Check if the AI pane is visible."""
        return self.is_displayed()

    def get_input(self) -> Optional[BaseComponent]:
        """Get the chat input area."""
        try:
            input_el = self.find_child(By.CSS_SELECTOR, '.composer-bar, [role="textbox"]')
            return BaseComponent(input_el)
        except NoSuchElementException:
            return None

    def send_message(self, message: str) -> None:
        """Send a message to the AI chat."""
        input_area = self.get_input()
        if input_area:
            input_area.click()
            ActionChains(self.driver).send_keys(message).perform()
            ActionChains(self.driver).key_down(MODIFIER_KEY).send_keys(Keys.ENTER).key_up(MODIFIER_KEY).perform()


class NotebookCellComponent(BaseComponent):
    """
    Jupyter Notebook cell in Cursor.
    """

    @property
    def cell_type(self) -> str:
        """Get the cell type (code or markdown)."""
        classes = self.get_attribute('class') or ''
        if 'code-cell' in classes:
            return 'code'
        elif 'markdown-cell' in classes:
            return 'markdown'
        return 'unknown'

    @property
    def is_focused(self) -> bool:
        """Check if this cell is focused."""
        classes = self.get_attribute('class') or ''
        return 'focused' in classes

    def execute(self) -> None:
        """
        Execute this cell using Ctrl+Enter.

        Note: This intentionally uses Ctrl (Keys.CONTROL) rather than Cmd
        to match the standard Jupyter-style notebook shortcut for executing
        a cell, even on macOS.
        """
        self.click()
        ActionChains(self.driver).key_down(Keys.CONTROL).send_keys(Keys.ENTER).key_up(Keys.CONTROL).perform()

    def delete(self) -> None:
        """Delete this cell."""
        self.click()
        ActionChains(self.driver).send_keys('d').send_keys('d').perform()


class CommandCenterComponent(BaseComponent):
    """
    Cursor's Command Center (top bar with project name).
    """

    @property
    def project_name(self) -> str:
        """Get the current project name."""
        return self.text.strip()

    def open_quick_open(self) -> None:
        """Open quick file open."""
        self.click()


class StatusBarComponent(BaseComponent):
    """
    Cursor's status bar at the bottom.
    """

    @property
    def items(self) -> List[BaseComponent]:
        """Get all status bar items."""
        item_elements = self.find_children(By.CSS_SELECTOR, '.statusbar-item-label')
        return [BaseComponent(el) for el in item_elements]

    def get_item(self, label: str) -> Optional[BaseComponent]:
        """Get a status bar item by its aria-label."""
        try:
            item = self.find_child(By.CSS_SELECTOR, f'[aria-label*="{label}"]')
            return BaseComponent(item)
        except NoSuchElementException:
            return None


# ============================================================================
# Main Cursor Page Object
# ============================================================================

class CursorPage(BasePage):
    """
    Page Object for the Cursor AI code editor.

    Provides high-level methods for interacting with Cursor.

    Example:
        from selectron import ElectronDriverManager
        from selectron.apps.cursor import CursorPage

        edm = ElectronDriverManager(app_name='Cursor')
        driver = edm.create_local_driver(debugging_port=9224)

        cursor = CursorPage(driver)
        cursor.open_file_quick_open()
        cursor.toggle_terminal()
        cursor.toggle_ai_pane()
    """

    def __init__(self, driver: WebDriver, timeout: float = 10.0):
        """
        Initialize Cursor page object.

        Args:
            driver: WebDriver instance connected to Cursor
            timeout: Default wait timeout
        """
        self._driver = driver
        self._wait = WebDriverWait(driver, timeout)
        self._component_wait = ComponentWait(driver, timeout)

        # Switch to main window
        self._switch_to_main_window()
        self.wait_for_page_load()

    def _switch_to_main_window(self) -> None:
        """Switch to the main Cursor window."""
        for handle in self._driver.window_handles:
            self._driver.switch_to.window(handle)
            # Cursor uses workbench.html
            if 'workbench.html' in self._driver.current_url:
                return
        # Fallback to last window if no match found
        if self._driver.window_handles:
            self._driver.switch_to.window(self._driver.window_handles[-1])

    @property
    def url_pattern(self) -> str:
        return 'workbench.html'

    def wait_for_page_load(self) -> None:
        """Wait for Cursor to be ready."""
        self._wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, '.monaco-workbench')
        ))

    # =============================================
    # CREATE Operations
    # =============================================

    def new_file(self) -> None:
        """Create a new file (Cmd/Ctrl+N)."""
        ActionChains(self._driver).key_down(MODIFIER_KEY).send_keys('n').key_up(MODIFIER_KEY).perform()

    def new_chat(self) -> None:
        """Start a new AI chat (Cmd+T in AI pane)."""
        try:
            new_chat_btn = self._driver.find_element(By.CSS_SELECTOR, '[aria-label*="New Chat"]')
            new_chat_btn.click()
        except NoSuchElementException:
            pass

    def add_code_cell(self) -> None:
        """Add a code cell in notebook view."""
        try:
            btn = self._driver.find_element(By.CSS_SELECTOR, '[aria-label*="Add Code Cell"]')
            btn.click()
        except NoSuchElementException:
            pass

    def add_markdown_cell(self) -> None:
        """Add a markdown cell in notebook view."""
        try:
            btn = self._driver.find_element(By.CSS_SELECTOR, '[aria-label*="Add Markdown Cell"]')
            btn.click()
        except NoSuchElementException:
            pass

    # =============================================
    # READ Operations
    # =============================================

    def open_file_quick_open(self) -> None:
        """Open the quick file open dialog (Cmd+P)."""
        ActionChains(self._driver).key_down(MODIFIER_KEY).send_keys('p').key_up(MODIFIER_KEY).perform()

    def show_chat_history(self) -> None:
        """Show the AI chat history."""
        try:
            btn = self._driver.find_element(By.CSS_SELECTOR, '[aria-label*="Show Chat History"]')
            btn.click()
        except NoSuchElementException:
            pass

    @property
    def problems_count(self) -> int:
        """Get the count of problems/errors."""
        try:
            problems = self._driver.find_element(By.CSS_SELECTOR, '[aria-label*="Problems"]')
            label = problems.get_attribute('aria-label') or ''
            # Parse "Problems (⌘NumPad0) - Total 9 Problems"
            if 'Total' in label:
                match = re.search(r'Total (\d+)', label)
                if match:
                    return int(match.group(1))
        except NoSuchElementException:
            pass
        return 0

    # =============================================
    # NAVIGATE Operations
    # =============================================

    def go_back(self) -> None:
        """Navigate back in history (Cmd+[)."""
        ActionChains(self._driver).key_down(MODIFIER_KEY).send_keys('[').key_up(MODIFIER_KEY).perform()

    def go_forward(self) -> None:
        """Navigate forward in history (Cmd+])."""
        ActionChains(self._driver).key_down(MODIFIER_KEY).send_keys(']').key_up(MODIFIER_KEY).perform()

    def open_terminal_panel(self) -> None:
        """Open the terminal panel."""
        try:
            terminal_tab = self._driver.find_element(By.CSS_SELECTOR, '[aria-label*="Terminal"]')
            terminal_tab.click()
        except NoSuchElementException:
            pass

    def open_problems_panel(self) -> None:
        """Open the problems panel."""
        try:
            problems_tab = self._driver.find_element(By.CSS_SELECTOR, 'a[aria-label*="Problems"]')
            problems_tab.click()
        except NoSuchElementException:
            pass

    def open_output_panel(self) -> None:
        """Open the output panel."""
        try:
            output_tab = self._driver.find_element(By.CSS_SELECTOR, 'a[aria-label*="Output"]')
            output_tab.click()
        except NoSuchElementException:
            pass

    # =============================================
    # UPDATE / TOGGLE Operations
    # =============================================

    def toggle_sidebar(self) -> None:
        """Toggle the primary sidebar (Cmd+B)."""
        ActionChains(self._driver).key_down(MODIFIER_KEY).send_keys('b').key_up(MODIFIER_KEY).perform()

    def toggle_panel(self) -> None:
        """Toggle the bottom panel (Cmd+J)."""
        ActionChains(self._driver).key_down(MODIFIER_KEY).send_keys('j').key_up(MODIFIER_KEY).perform()

    def toggle_ai_pane(self) -> None:
        """Toggle the AI pane (Alt+Cmd+B)."""
        ActionChains(self._driver).key_down(Keys.ALT).key_down(MODIFIER_KEY).send_keys('b').key_up(MODIFIER_KEY).key_up(Keys.ALT).perform()

    def change_layout(self) -> None:
        """Open the layout change menu."""
        try:
            btn = self._driver.find_element(By.CSS_SELECTOR, '[aria-label="Change Layout"]')
            btn.click()
        except NoSuchElementException:
            pass

    # =============================================
    # DELETE Operations
    # =============================================

    def clear_all_outputs(self) -> None:
        """Clear all notebook outputs."""
        try:
            btn = self._driver.find_element(By.CSS_SELECTOR, '[aria-label*="Clear All Outputs"]')
            btn.click()
        except NoSuchElementException:
            pass

    def delete_cell(self) -> None:
        """Delete the current notebook cell."""
        try:
            btn = self._driver.find_element(By.CSS_SELECTOR, '[aria-label*="Delete Cell"]')
            btn.click()
        except NoSuchElementException:
            # Keyboard shortcut: D D (vim-style)
            ActionChains(self._driver).send_keys('d').send_keys('d').perform()

    def clear_notification(self) -> None:
        """Clear the current notification."""
        try:
            btn = self._driver.find_element(By.CSS_SELECTOR, '[aria-label*="Clear Notification"]')
            btn.click()
        except NoSuchElementException:
            pass

    # =============================================
    # Editor Tabs
    # =============================================

    @property
    def editor_tabs(self) -> List[EditorTabComponent]:
        """Get all open editor tabs."""
        tab_elements = self._driver.find_elements(By.CSS_SELECTOR, '[role="tab"].tab')
        return [EditorTabComponent(el) for el in tab_elements]

    @property
    def active_tab(self) -> Optional[EditorTabComponent]:
        """Get the currently active editor tab."""
        for tab in self.editor_tabs:
            if tab.is_active:
                return tab
        return None

    def switch_to_tab(self, filename: str) -> bool:
        """Switch to a tab by filename."""
        for tab in self.editor_tabs:
            if tab.filename == filename:
                tab.activate()
                return True
        return False

    def close_tab(self, filename: str) -> bool:
        """Close a tab by filename."""
        for tab in self.editor_tabs:
            if tab.filename == filename:
                tab.close()
                return True
        return False

    # =============================================
    # File Explorer
    # =============================================

    @property
    def file_explorer(self) -> Optional[FileExplorerComponent]:
        """Get the file explorer component."""
        try:
            explorer = self._driver.find_element(By.CSS_SELECTOR, '[aria-label="Files Explorer"]')
            return FileExplorerComponent(explorer)
        except NoSuchElementException:
            return None

    # =============================================
    # Terminal
    # =============================================

    @property
    def terminal(self) -> Optional[TerminalComponent]:
        """Get the terminal component."""
        try:
            terminal = self._driver.find_element(By.CSS_SELECTOR, '.terminal-wrapper, .xterm')
            return TerminalComponent(terminal)
        except NoSuchElementException:
            return None

    def toggle_terminal(self) -> None:
        """Toggle the integrated terminal (Ctrl+`)."""
        ActionChains(self._driver).key_down(Keys.CONTROL).send_keys('`').key_up(Keys.CONTROL).perform()

    # =============================================
    # AI Chat
    # =============================================

    @property
    def ai_chat(self) -> Optional[AIChatComponent]:
        """Get the AI chat component."""
        try:
            chat = self._driver.find_element(By.CSS_SELECTOR, '.composer-bar, .aichat-container')
            return AIChatComponent(chat)
        except NoSuchElementException:
            return None

    def send_ai_message(self, message: str) -> None:
        """Send a message to the AI chat."""
        chat = self.ai_chat
        if chat:
            chat.send_message(message)

    # =============================================
    # Command Palette
    # =============================================

    def open_command_palette(self) -> None:
        """Open the command palette (Cmd+Shift+P)."""
        ActionChains(self._driver).key_down(MODIFIER_KEY).key_down(Keys.SHIFT).send_keys('p').key_up(Keys.SHIFT).key_up(MODIFIER_KEY).perform()

    def run_command(self, command_name: str) -> None:
        """Run a command by name via the command palette."""
        self.open_command_palette()
        try:
            self._wait.until(EC.visibility_of_element_located(
                (By.CSS_SELECTOR, '.quick-input-widget input')
            ))
            input_el = self._driver.find_element(By.CSS_SELECTOR, '.quick-input-widget input')
            input_el.clear()
            input_el.send_keys(command_name)
            # Wait for command palette search results to appear
            try:
                self._wait.until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, '.quick-input-list .monaco-list-row')
                ))
            except TimeoutException:
                # If no results appear within timeout, still attempt to run the command
                pass
            ActionChains(self._driver).send_keys(Keys.ENTER).perform()
        except TimeoutException:
            pass

    # =============================================
    # Notebook Operations
    # =============================================

    @property
    def notebook_cells(self) -> List[NotebookCellComponent]:
        """Get all notebook cells (when a notebook is open)."""
        cell_elements = self._driver.find_elements(By.CSS_SELECTOR, '.monaco-list-row[role="listitem"]')
        return [NotebookCellComponent(el) for el in cell_elements]

    def run_all_cells(self) -> None:
        """Run all notebook cells."""
        try:
            btn = self._driver.find_element(By.CSS_SELECTOR, '[aria-label="Run All"]')
            btn.click()
        except NoSuchElementException:
            pass

    def restart_kernel(self) -> None:
        """Restart the Jupyter kernel."""
        try:
            btn = self._driver.find_element(By.CSS_SELECTOR, '[aria-label*="Restart"]')
            btn.click()
        except NoSuchElementException:
            pass

    # =============================================
    # Status Bar
    # =============================================

    @property
    def status_bar(self) -> Optional[StatusBarComponent]:
        """Get the status bar component."""
        try:
            status_bar = self._driver.find_element(By.ID, 'workbench.parts.statusbar')
            return StatusBarComponent(status_bar)
        except NoSuchElementException:
            return None

    # =============================================
    # Utilities
    # =============================================

    def save(self) -> None:
        """Save the current file (Cmd+S)."""
        ActionChains(self._driver).key_down(MODIFIER_KEY).send_keys('s').key_up(MODIFIER_KEY).perform()

    def save_all(self) -> None:
        """Save all open files (Cmd+Alt+S)."""
        ActionChains(self._driver).key_down(MODIFIER_KEY).key_down(Keys.ALT).send_keys('s').key_up(Keys.ALT).key_up(MODIFIER_KEY).perform()

    def close_file(self) -> None:
        """Close the current file (Cmd+W)."""
        ActionChains(self._driver).key_down(MODIFIER_KEY).send_keys('w').key_up(MODIFIER_KEY).perform()

    def open_settings(self) -> None:
        """Open settings (Cmd+,)."""
        ActionChains(self._driver).key_down(MODIFIER_KEY).send_keys(',').key_up(MODIFIER_KEY).perform()

    def screenshot(self, filename: str) -> bool:
        """Take a screenshot of the Cursor window."""
        return self._driver.save_screenshot(filename)
