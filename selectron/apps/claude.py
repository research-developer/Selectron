"""
Claude Desktop App Page Object Model

Provides a high-level interface for automating the Claude desktop application
using W3C WebDriver/WebElement component patterns.
"""

import platform
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
    MenuComponent,
    ComponentWait,
)
from ..driver import send_shortcut


class ChatInputComponent(BaseComponent):
    """
    Claude's chat input component.

    Handles message composition and sending.
    """

    @property
    def is_ready(self) -> bool:
        """Check if the input is ready for typing."""
        return self.is_displayed() and self.is_enabled()

    def type_message(self, message: str) -> None:
        """
        Type a message into the chat input.

        Args:
            message: The message to type
        """
        # Click to focus first
        self._root.click()
        # Select all and replace (clear() doesn't work on some textareas)
        ActionChains(self.driver).key_down(MODIFIER_KEY).send_keys('a').key_up(MODIFIER_KEY).perform()
        self._root.send_keys(message)

    def send(self) -> None:
        """Send the current message (Cmd/Ctrl+Enter or click send button)."""
        ActionChains(self.driver).key_down(MODIFIER_KEY).send_keys(Keys.ENTER).key_up(MODIFIER_KEY).perform()

    def type_and_send(self, message: str) -> None:
        """Type a message and send it."""
        self.type_message(message)
        self.send()

    @property
    def current_text(self) -> str:
        """Get the current text in the input."""
        return self._root.text or self._root.get_attribute('value') or ''


class ConversationComponent(BaseComponent):
    """
    A conversation/chat thread in Claude.
    """

    @property
    def messages(self) -> List['MessageComponent']:
        """Get all messages in this conversation."""
        # Common patterns for message containers
        message_elements = self.find_children(By.CSS_SELECTOR,
            '[data-message], .message, [class*="message"]')
        return [MessageComponent(el) for el in message_elements]

    @property
    def last_message(self) -> Optional['MessageComponent']:
        """Get the most recent message."""
        messages = self.messages
        return messages[-1] if messages else None

    def wait_for_response(self, timeout: float = 60.0) -> Optional['MessageComponent']:
        """
        Wait for Claude to finish responding.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            The response message component, or None if timed out
        """
        wait = WebDriverWait(self.driver, timeout)
        try:
            # Wait for streaming to stop (look for stop button to disappear)
            wait.until(EC.invisibility_of_element_located(
                (By.CSS_SELECTOR, '[aria-label*="Stop"], .stop-button')
            ))
            return self.last_message
        except TimeoutException:
            return None


class MessageComponent(BaseComponent):
    """
    A single message in a Claude conversation.
    """

    @property
    def role(self) -> str:
        """Get the message role (user or assistant)."""
        # Try to determine from attributes or position
        classes = self.get_attribute('class') or ''
        if 'user' in classes.lower():
            return 'user'
        elif 'assistant' in classes.lower() or 'claude' in classes.lower():
            return 'assistant'
        return 'unknown'

    @property
    def content(self) -> str:
        """Get the message content text."""
        return self.text

    @property
    def is_streaming(self) -> bool:
        """Check if this message is still being streamed."""
        classes = self.get_attribute('class') or ''
        return 'streaming' in classes.lower()

    def copy_to_clipboard(self) -> None:
        """Copy the message content to clipboard."""
        try:
            copy_btn = self.find_child(By.CSS_SELECTOR, '[aria-label*="Copy"], .copy-button')
            copy_btn.click()
        except NoSuchElementException:
            # No reliable fallback available for copying from a non-editable container.
            # If the UI does not expose a copy button, this operation is a no-op.
            pass


class SidebarComponent(BaseComponent):
    """
    Claude's sidebar with conversation list.
    """

    @property
    def is_open(self) -> bool:
        """Check if the sidebar is open."""
        return self.is_displayed()

    def toggle(self) -> None:
        """Toggle the sidebar open/closed."""
        send_shortcut(self.driver, 'b', Keys.COMMAND)

    @property
    def conversations(self) -> List[BaseComponent]:
        """Get all conversation items in the sidebar."""
        items = self.find_children(By.CSS_SELECTOR,
            '[data-conversation], .conversation-item, [class*="conversation"]')
        return [BaseComponent(el) for el in items]

    def new_chat(self) -> None:
        """Start a new chat."""
        send_shortcut(self.driver, 'n', Keys.COMMAND)

    def search(self, query: str) -> None:
        """Search conversations."""
        send_shortcut(self.driver, 'k', Keys.COMMAND)
        # Wait for search to appear and type
        wait = WebDriverWait(self.driver, 5)
        search_input = wait.until(EC.visibility_of_element_located(
            (By.CSS_SELECTOR, 'input[type="search"], input[placeholder*="Search"]')
        ))
        search_input.send_keys(query)


class ClaudePage(BasePage):
    """
    Page Object for the Claude desktop application.

    Provides high-level methods for interacting with Claude.

    Example:
        from selectron import ElectronDriverManager
        from selectron.apps.claude import ClaudePage

        edm = ElectronDriverManager(app_name='Claude')
        driver = edm.create_local_driver(debugging_port=9222)

        claude = ClaudePage(driver)
        claude.new_chat()
        claude.send_message("Hello, Claude!")
        response = claude.wait_for_response()
        print(response.content)
    """

    def __init__(self, driver: WebDriver, timeout: float = 10.0):
        """
        Initialize Claude page object.

        Args:
            driver: WebDriver instance connected to Claude
            timeout: Default wait timeout
        """
        self._driver = driver
        self._wait = WebDriverWait(driver, timeout)
        self._component_wait = ComponentWait(driver, timeout)

        # Switch to main window
        self._switch_to_main_window()
        self.wait_for_page_load()

    def _switch_to_main_window(self) -> None:
        """Switch to the main Claude window."""
        for handle in self._driver.window_handles:
            self._driver.switch_to.window(handle)
            if 'Claude' in self._driver.title:
                return
        # If no titled window found, use the last one
        if self._driver.window_handles:
            self._driver.switch_to.window(self._driver.window_handles[-1])

    @property
    def url_pattern(self) -> str:
        return 'Claude'

    def wait_for_page_load(self) -> None:
        """Wait for Claude to be ready."""
        self._wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, '#root, body')
        ))

    # Chat Input
    @property
    def chat_input(self) -> Optional[ChatInputComponent]:
        """Get the chat input component."""
        try:
            textarea = self._driver.find_element(By.CSS_SELECTOR, 'textarea')
            return ChatInputComponent(textarea)
        except NoSuchElementException:
            return None

    def send_message(self, message: str) -> None:
        """
        Send a message to Claude.

        Args:
            message: The message to send
        """
        chat = self.chat_input
        if chat:
            chat.type_and_send(message)
        else:
            raise RuntimeError("Chat input not found")

    def wait_for_response(self, timeout: float = 60.0) -> Optional[str]:
        """
        Wait for Claude to finish responding and return the response.

        Args:
            timeout: Maximum time to wait

        Returns:
            The response text, or None if timed out
        """
        wait = WebDriverWait(self._driver, timeout)
        try:
            # Wait for the streaming "Stop" control to disappear
            # This is a more explicit indicator that the response is complete
            wait.until(EC.invisibility_of_element_located(
                (By.CSS_SELECTOR, 'button[aria-label*="Stop"]')
            ))
            # Get the last assistant message
            messages = self._driver.find_elements(By.CSS_SELECTOR,
                '[class*="assistant"], [class*="response"]')
            if messages:
                return messages[-1].text
        except TimeoutException:
            pass
        return None

    # Sidebar
    def toggle_sidebar(self) -> None:
        """Toggle the sidebar."""
        send_shortcut(self._driver, 'b', Keys.COMMAND)

    def new_chat(self) -> None:
        """Start a new chat."""
        send_shortcut(self._driver, 'n', Keys.COMMAND)

    def search_chats(self, query: str) -> None:
        """
        Open search and search for chats.

        Args:
            query: Search query
        """
        send_shortcut(self._driver, 'k', Keys.COMMAND)
        self._wait.until(EC.visibility_of_element_located(
            (By.CSS_SELECTOR, 'input[type="search"], input')
        )).send_keys(query)

    # Model Selection
    def get_current_model(self) -> str:
        """Get the currently selected model."""
        try:
            model_btn = self._driver.find_element(By.CSS_SELECTOR,
                'button[aria-label*="model"], button[class*="model"]')
            return model_btn.text
        except NoSuchElementException:
            return "Unknown"

    # Buttons
    def get_button(self, label: str) -> Optional[ButtonComponent]:
        """
        Get a button by its label or aria-label.

        Args:
            label: Button text or aria-label

        Returns:
            ButtonComponent or None
        """
        try:
            btn = self._driver.find_element(By.XPATH,
                f'//button[contains(text(), "{label}") or contains(@aria-label, "{label}")]')
            return ButtonComponent(btn)
        except NoSuchElementException:
            return None

    def click_button(self, label: str) -> bool:
        """
        Click a button by its label.

        Args:
            label: Button text or aria-label

        Returns:
            True if clicked, False if not found
        """
        btn = self.get_button(label)
        if btn:
            btn.click()
            return True
        return False

    # Keyboard Shortcuts
    def open_settings(self) -> None:
        """Open settings (Cmd+,)."""
        send_shortcut(self._driver, ',', Keys.COMMAND)

    def open_command_palette(self) -> None:
        """Open command palette (Cmd+Shift+P or Cmd+K)."""
        send_shortcut(self._driver, 'k', Keys.COMMAND)

    # Screenshot
    def screenshot(self, filename: str) -> bool:
        """Take a screenshot of the Claude window."""
        return self._driver.save_screenshot(filename)
