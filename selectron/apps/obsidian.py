"""
Obsidian App Page Object Model

Provides a high-level interface for automating the Obsidian note-taking application
using W3C WebDriver/WebElement component patterns.

Generated from SLTT classifier scan with 76 elements classified.
"""

from typing import Optional, List
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException

from ..components import (
    BasePage,
    BaseComponent,
    ButtonComponent,
    LinkComponent,
    ModalComponent,
    SearchComponent,
    ComponentWait,
)


# ============================================================================
# Obsidian-Specific Component Classes
# ============================================================================

class RibbonActionComponent(BaseComponent):
    """
    Obsidian's left ribbon action button.

    These are the clickable icons in the left sidebar ribbon.
    """

    @property
    def label(self) -> str:
        """Get the aria-label of the action."""
        return self.get_attribute('aria-label') or ''

    def activate(self) -> None:
        """Activate/click this ribbon action."""
        self.click()


class TabHeaderComponent(BaseComponent):
    """
    Obsidian's workspace tab header.

    Represents an open note/view tab in the workspace.
    """

    @property
    def title(self) -> str:
        """Get the tab title (aria-label)."""
        return self.get_attribute('aria-label') or self.text

    @property
    def is_active(self) -> bool:
        """Check if this tab is currently active."""
        classes = self.get_attribute('class') or ''
        return 'is-active' in classes or 'mod-active' in classes

    def activate(self) -> None:
        """Click to switch to this tab."""
        self.click()

    def close(self) -> None:
        """Close this tab via middle-click."""
        ActionChains(self.driver).move_to_element(self._root).click(button=1).perform()


class QuickSwitcherComponent(BaseComponent):
    """
    Obsidian's Quick Switcher modal.

    Allows fast navigation between notes.
    """

    @property
    def is_open(self) -> bool:
        """Check if the quick switcher is visible."""
        return self.is_displayed()

    @property
    def search_input(self) -> Optional[BaseComponent]:
        """Get the search input field."""
        try:
            input_el = self.find_child(By.CSS_SELECTOR, 'input[type="text"], input')
            return BaseComponent(input_el)
        except NoSuchElementException:
            return None

    def search(self, query: str) -> None:
        """Search for a note by name."""
        search_input = self.search_input
        if search_input:
            search_input._root.clear()
            search_input._root.send_keys(query)

    def select_first_result(self) -> None:
        """Select the first search result."""
        ActionChains(self.driver).send_keys(Keys.ENTER).perform()

    def close(self) -> None:
        """Close the quick switcher."""
        ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()


class CommandPaletteComponent(BaseComponent):
    """
    Obsidian's Command Palette modal.

    Provides access to all available commands.
    """

    @property
    def is_open(self) -> bool:
        """Check if command palette is visible."""
        return self.is_displayed()

    def search_command(self, query: str) -> None:
        """Search for a command."""
        try:
            input_el = self.find_child(By.CSS_SELECTOR, 'input')
            input_el.clear()
            input_el.send_keys(query)
        except NoSuchElementException:
            pass

    def execute_first(self) -> None:
        """Execute the first matching command."""
        ActionChains(self.driver).send_keys(Keys.ENTER).perform()

    def close(self) -> None:
        """Close the command palette."""
        ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()


class FileExplorerComponent(BaseComponent):
    """
    Obsidian's File Explorer panel.

    Shows the vault's file structure.
    """

    @property
    def files(self) -> List[BaseComponent]:
        """Get all visible file items."""
        file_elements = self.find_children(By.CSS_SELECTOR, '.nav-file-title')
        return [BaseComponent(el) for el in file_elements]

    @property
    def folders(self) -> List[BaseComponent]:
        """Get all visible folder items."""
        folder_elements = self.find_children(By.CSS_SELECTOR, '.nav-folder-title')
        return [BaseComponent(el) for el in folder_elements]

    def open_file(self, name: str) -> bool:
        """Open a file by name."""
        for file in self.files:
            if file.text == name:
                file.click()
                return True
        return False

    def expand_folder(self, name: str) -> bool:
        """Expand a folder by name."""
        for folder in self.folders:
            if folder.text == name:
                folder.click()
                return True
        return False


class EditorComponent(BaseComponent):
    """
    Obsidian's Note Editor.

    Handles text editing in the active note.
    """

    @property
    def content(self) -> str:
        """Get the current editor content."""
        return self.text

    def type_text(self, text: str) -> None:
        """Type text into the editor."""
        self.click()
        ActionChains(self.driver).send_keys(text).perform()

    def select_all(self) -> None:
        """Select all text."""
        ActionChains(self.driver).key_down(Keys.COMMAND).send_keys('a').key_up(Keys.COMMAND).perform()

    def copy(self) -> None:
        """Copy selected text."""
        ActionChains(self.driver).key_down(Keys.COMMAND).send_keys('c').key_up(Keys.COMMAND).perform()

    def paste(self) -> None:
        """Paste from clipboard."""
        ActionChains(self.driver).key_down(Keys.COMMAND).send_keys('v').key_up(Keys.COMMAND).perform()


# ============================================================================
# Main Obsidian Page Object
# ============================================================================

class ObsidianPage(BasePage):
    """
    Page Object for the Obsidian note-taking application.

    Provides high-level methods for interacting with Obsidian.

    Example:
        from selectron import ElectronDriverManager
        from selectron.apps.obsidian import ObsidianPage

        edm = ElectronDriverManager(app_name='Obsidian')
        driver = edm.create_local_driver(debugging_port=9223)

        obsidian = ObsidianPage(driver)
        obsidian.open_quick_switcher()
        obsidian.quick_switcher.search("My Note")
        obsidian.quick_switcher.select_first_result()
    """

    def __init__(self, driver: WebDriver, timeout: float = 10.0):
        """
        Initialize Obsidian page object.

        Args:
            driver: WebDriver instance connected to Obsidian
            timeout: Default wait timeout
        """
        self._driver = driver
        self._wait = WebDriverWait(driver, timeout)
        self._component_wait = ComponentWait(driver, timeout)

        # Switch to main window
        self._switch_to_main_window()
        self.wait_for_page_load()

    def _switch_to_main_window(self) -> None:
        """Switch to the main Obsidian window."""
        for handle in self._driver.window_handles:
            self._driver.switch_to.window(handle)
            if 'Obsidian' in self._driver.title:
                return
        # If no titled window found, use the last one
        self._driver.switch_to.window(self._driver.window_handles[-1])

    @property
    def url_pattern(self) -> str:
        return 'Obsidian'

    def wait_for_page_load(self) -> None:
        """Wait for Obsidian to be ready."""
        self._wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, '.app-container, body')
        ))

    # =============================================
    # CREATE Operations
    # =============================================

    def create_new_note(self) -> None:
        """Create a new note (Cmd+N)."""
        ActionChains(self._driver).key_down(Keys.COMMAND).send_keys('n').key_up(Keys.COMMAND).perform()

    def create_new_canvas(self) -> None:
        """Create a new canvas via ribbon action."""
        self._click_ribbon_action("Create new canvas")

    def create_new_board(self) -> None:
        """Create a new board (Kanban) via ribbon action."""
        self._click_ribbon_action("Create new board")

    def create_new_unique_note(self) -> None:
        """Create a new unique note via ribbon action."""
        self._click_ribbon_action("Create new unique note")

    def insert_template(self) -> None:
        """Insert a template via ribbon action."""
        self._click_ribbon_action("Insert template")

    def create_new_tab(self) -> None:
        """Create a new tab."""
        try:
            new_tab = self._driver.find_element(By.CSS_SELECTOR, '[aria-label="New tab"]')
            new_tab.click()
        except NoSuchElementException:
            # Fallback to keyboard shortcut
            ActionChains(self._driver).key_down(Keys.COMMAND).send_keys('t').key_up(Keys.COMMAND).perform()

    # =============================================
    # READ / OPEN Operations
    # =============================================

    def open_quick_switcher(self) -> None:
        """Open the quick switcher (Cmd+O)."""
        ActionChains(self._driver).key_down(Keys.COMMAND).send_keys('o').key_up(Keys.COMMAND).perform()

    @property
    def quick_switcher(self) -> Optional[QuickSwitcherComponent]:
        """Get the quick switcher component if open."""
        try:
            modal = self._driver.find_element(By.CSS_SELECTOR, '.prompt')
            return QuickSwitcherComponent(modal)
        except NoSuchElementException:
            return None

    def open_graph_view(self) -> None:
        """Open the graph view via ribbon action."""
        self._click_ribbon_action("Open graph view")

    def open_daily_note(self) -> None:
        """Open today's daily note via ribbon action."""
        self._click_ribbon_action("Open today's daily note")

    def open_command_palette(self) -> None:
        """Open the command palette (Cmd+P)."""
        ActionChains(self._driver).key_down(Keys.COMMAND).send_keys('p').key_up(Keys.COMMAND).perform()

    @property
    def command_palette(self) -> Optional[CommandPaletteComponent]:
        """Get the command palette component if open."""
        try:
            modal = self._driver.find_element(By.CSS_SELECTOR, '.prompt')
            return CommandPaletteComponent(modal)
        except NoSuchElementException:
            return None

    def open_format_converter(self) -> None:
        """Open the format converter via ribbon action."""
        self._click_ribbon_action("Open format converter")

    def open_smart_connections(self) -> None:
        """Open Smart Connections view via ribbon action."""
        self._click_ribbon_action("Smart Connections: Open connections view")

    def open_smart_lookup(self) -> None:
        """Open Smart Lookup view via ribbon action."""
        self._click_ribbon_action("Smart Lookup: Open lookup view")

    # =============================================
    # NAVIGATE Operations
    # =============================================

    def navigate_back(self) -> None:
        """Navigate back in history."""
        try:
            back_btn = self._driver.find_element(By.CSS_SELECTOR, '[aria-label="Navigate back"]')
            back_btn.click()
        except NoSuchElementException:
            ActionChains(self._driver).key_down(Keys.COMMAND).send_keys('[').key_up(Keys.COMMAND).perform()

    def navigate_forward(self) -> None:
        """Navigate forward in history."""
        try:
            forward_btn = self._driver.find_element(By.CSS_SELECTOR, '[aria-label="Navigate forward"]')
            forward_btn.click()
        except NoSuchElementException:
            ActionChains(self._driver).key_down(Keys.COMMAND).send_keys(']').key_up(Keys.COMMAND).perform()

    def open_search(self) -> None:
        """Open the search panel."""
        self._click_workspace_tab("Search")

    def open_files(self) -> None:
        """Open the files panel."""
        self._click_workspace_tab("Files")

    def open_bookmarks(self) -> None:
        """Open the bookmarks panel."""
        self._click_workspace_tab("Bookmarks")

    def open_backlinks(self) -> None:
        """Open the backlinks panel."""
        self._click_workspace_tab("Backlinks")

    def open_tags(self) -> None:
        """Open the tags panel."""
        self._click_workspace_tab("Tags")

    # =============================================
    # UPDATE Operations
    # =============================================

    def publish_changes(self) -> None:
        """Open the publish changes dialog via ribbon action."""
        self._click_ribbon_action("Publish changes...")

    def change_sort_order(self) -> None:
        """Open sort order options."""
        try:
            btn = self._driver.find_element(By.CSS_SELECTOR, '[aria-label="Change sort order"]')
            btn.click()
        except NoSuchElementException:
            pass

    def open_more_options(self) -> None:
        """Open the more options menu."""
        try:
            btn = self._driver.find_element(By.CSS_SELECTOR, '[aria-label="More options"]')
            btn.click()
        except NoSuchElementException:
            pass

    # =============================================
    # Workspace & Tabs
    # =============================================

    @property
    def tabs(self) -> List[TabHeaderComponent]:
        """Get all open workspace tabs."""
        tab_elements = self._driver.find_elements(By.CSS_SELECTOR, '.workspace-tab-header.tappable')
        return [TabHeaderComponent(el) for el in tab_elements]

    @property
    def active_tab(self) -> Optional[TabHeaderComponent]:
        """Get the currently active tab."""
        for tab in self.tabs:
            if tab.is_active:
                return tab
        return None

    def switch_to_tab(self, title: str) -> bool:
        """Switch to a tab by its title."""
        for tab in self.tabs:
            if tab.title == title:
                tab.activate()
                return True
        return False

    @property
    def file_explorer(self) -> Optional[FileExplorerComponent]:
        """Get the file explorer component."""
        try:
            explorer = self._driver.find_element(By.CSS_SELECTOR, '.nav-files-container')
            return FileExplorerComponent(explorer)
        except NoSuchElementException:
            return None

    @property
    def editor(self) -> Optional[EditorComponent]:
        """Get the active editor component."""
        try:
            editor = self._driver.find_element(By.CSS_SELECTOR, '.cm-content, .markdown-source-view')
            return EditorComponent(editor)
        except NoSuchElementException:
            return None

    # =============================================
    # Ribbon Actions
    # =============================================

    @property
    def ribbon_actions(self) -> List[RibbonActionComponent]:
        """Get all ribbon action buttons."""
        action_elements = self._driver.find_elements(
            By.CSS_SELECTOR, '.side-dock-ribbon-action'
        )
        return [RibbonActionComponent(el) for el in action_elements]

    def _click_ribbon_action(self, label: str) -> bool:
        """Click a ribbon action by its aria-label."""
        try:
            action = self._driver.find_element(By.CSS_SELECTOR, f'[aria-label="{label}"]')
            action.click()
            return True
        except NoSuchElementException:
            return False

    def _click_workspace_tab(self, label: str) -> bool:
        """Click a workspace tab by its aria-label."""
        try:
            tab = self._driver.find_element(By.CSS_SELECTOR, f'.workspace-tab-header[aria-label="{label}"]')
            tab.click()
            return True
        except NoSuchElementException:
            return False

    # =============================================
    # Settings & Utilities
    # =============================================

    def open_settings(self) -> None:
        """Open settings (Cmd+,)."""
        ActionChains(self._driver).key_down(Keys.COMMAND).send_keys(',').key_up(Keys.COMMAND).perform()

    def toggle_left_sidebar(self) -> None:
        """Toggle the left sidebar."""
        ActionChains(self._driver).key_down(Keys.COMMAND).send_keys('\\').key_up(Keys.COMMAND).perform()

    def toggle_right_sidebar(self) -> None:
        """Toggle the right sidebar."""
        ActionChains(self._driver).key_down(Keys.COMMAND).key_down(Keys.SHIFT).send_keys('\\').key_up(Keys.SHIFT).key_up(Keys.COMMAND).perform()

    def screenshot(self, filename: str) -> bool:
        """Take a screenshot of the Obsidian window."""
        return self._driver.save_screenshot(filename)

    def run_command(self, command_name: str) -> None:
        """Run a command by name via the command palette."""
        self.open_command_palette()
        try:
            self._wait.until(EC.visibility_of_element_located(
                (By.CSS_SELECTOR, '.prompt input')
            ))
            palette = self.command_palette
            if palette:
                palette.search_command(command_name)
                import time
                time.sleep(0.3)  # Wait for search results
                palette.execute_first()
        except TimeoutException:
            pass
