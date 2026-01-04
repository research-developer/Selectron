"""
Claude Page Object - JSON-Based POM

Thin wrapper around the JSON-defined elements and operations.
Provides type hints and additional convenience methods.

Usage:
    from poms.Claude.claude_page import ClaudePage

    # With driver
    claude = ClaudePage(driver)
    claude.create_new_chat()
    claude.type_message(text="Hello Claude!")
    claude.send_message()
    response = claude.wait_for_response()

    # iPython exploration
    from poms.Claude.claude_page import load_claude_elements
    elements = load_claude_elements()
    print(elements['new_chat_btn'])
"""

from pathlib import Path
from typing import Optional, List, Any
import json

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Import the loader - handle both installed and local development
try:
    from selectron.pom_loader import POMLoader, BasePOM, POMData
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from selectron.pom_loader import POMLoader, BasePOM, POMData


# Path to this POM's directory
POM_DIR = Path(__file__).parent


def load_claude_elements() -> dict:
    """
    Load Claude elements for inspection (no driver needed).

    Useful for iPython exploration.

    Returns:
        Dictionary mapping element IDs to element definitions
    """
    with open(POM_DIR / 'elements.json', 'r') as f:
        data = json.load(f)
    return {elem['id']: elem for elem in data.get('elements', [])}


def load_claude_operations() -> dict:
    """
    Load Claude operations for inspection (no driver needed).

    Returns:
        Dictionary mapping operation names to operation definitions
    """
    with open(POM_DIR / 'operations.json', 'r') as f:
        data = json.load(f)
    return {op['name']: op for op in data.get('operations', [])}


class ClaudePage(BasePOM):
    """
    Page Object for Claude AI assistant.

    Extends BasePOM with Claude-specific convenience methods.
    All operations from operations.json are available as methods.

    Example:
        claude = ClaudePage(driver)

        # Use generated methods
        claude.create_new_chat()
        claude.type_message(text="Hello!")
        claude.send_message()

        # Or use execute_operation directly
        claude.execute_operation('send_message')

        # Access elements
        elem = claude.find_element('chat_textarea')
    """

    def __init__(self, driver: WebDriver, timeout: float = 10.0):
        """
        Initialize Claude Page Object.

        Args:
            driver: WebDriver instance connected to Claude
            timeout: Default wait timeout in seconds
        """
        pom_data = POMData('Claude', POM_DIR).load()
        super().__init__(driver, pom_data, timeout)

        # Switch to main Claude window if multiple handles
        self._switch_to_claude_window()

    def _switch_to_claude_window(self) -> None:
        """Switch to the main Claude window."""
        for handle in self._driver.window_handles:
            self._driver.switch_to.window(handle)
            if 'Claude' in self._driver.title:
                return
        # If no titled window, use last one
        if self._driver.window_handles:
            self._driver.switch_to.window(self._driver.window_handles[-1])

    # =========================================
    # Convenience Methods (beyond JSON ops)
    # =========================================

    def send_chat_message(self, message: str, wait_for_response: bool = True) -> Optional[str]:
        """
        Complete flow: type message, send, and optionally wait for response.

        Args:
            message: The message to send
            wait_for_response: Whether to wait for Claude's response

        Returns:
            The response text if wait_for_response=True, else None
        """
        # Focus and type using ActionChains (Claude's ProseMirror editor)
        container = self.find_element('chat_input_container')
        if container:
            self._driver.execute_script('arguments[0].click();', container)
            ActionChains(self._driver).send_keys(message).perform()

        # Click send
        self.send_message()

        if wait_for_response:
            try:
                self.wait_for_response()
                return self.get_last_response_text()
            except Exception:
                return None

        return None

    def get_last_response_text(self) -> Optional[str]:
        """Get the text content of the last assistant response."""
        try:
            messages = self._driver.find_elements(
                By.CSS_SELECTOR, '[class*="assistant"], [class*="response"]'
            )
            if messages:
                return messages[-1].text
        except Exception:
            pass
        return None

    def get_all_messages(self) -> List[dict]:
        """
        Get all messages in the current conversation.

        Returns:
            List of dicts with 'role' and 'content' keys
        """
        messages = []
        try:
            # Try to find user messages
            user_msgs = self._driver.find_elements(
                By.CSS_SELECTOR, '[class*="user"]'
            )
            for msg in user_msgs:
                messages.append({'role': 'user', 'content': msg.text})

            # Try to find assistant messages
            assistant_msgs = self._driver.find_elements(
                By.CSS_SELECTOR, '[class*="assistant"], [class*="response"]'
            )
            for msg in assistant_msgs:
                messages.append({'role': 'assistant', 'content': msg.text})

        except Exception:
            pass

        return messages

    def is_generating(self) -> bool:
        """Check if Claude is currently generating a response."""
        try:
            stop_btn = self.find_element('stop_btn')
            return stop_btn is not None and stop_btn.is_displayed()
        except Exception:
            return False

    def get_current_model(self) -> str:
        """Get the currently selected model name."""
        try:
            model_btn = self.find_element('model_selector')
            if model_btn:
                return model_btn.text
        except Exception:
            pass
        return "Unknown"

    def search_chats(self, query: str) -> None:
        """
        Search for chats using the search dialog.

        Args:
            query: Search query string
        """
        self.open_search()
        WebDriverWait(self._driver, 5).until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, 'input[type="search"], input')
            )
        )
        search_input = self.find_element('search_input')
        if search_input:
            search_input.clear()
            search_input.send_keys(query)


# Convenience function for quick loading
def load(driver: WebDriver, timeout: float = 10.0) -> ClaudePage:
    """
    Quick loader for ClaudePage.

    Usage:
        from poms.Claude import claude_page
        claude = claude_page.load(driver)
    """
    return ClaudePage(driver, timeout)
