"""
Selectron Components

W3C WebDriver/WebElement component architecture for Electron app automation.
Implements ActionDelegate (form components) and NavDelegate (navigation components).
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Callable, TypeVar, Generic, Any
from dataclasses import dataclass
from enum import Enum

from selenium import webdriver
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    ElementNotInteractableException,
)


T = TypeVar('T', bound='BaseComponent')


# ============================================================================
# Base Component Classes
# ============================================================================

class BaseComponent:
    """
    Base class for all UI components.

    Components encapsulate a root WebElement and provide semantic methods
    for interacting with it. Use scoped finding for child elements.

    Example:
        class LoginForm(BaseComponent):
            def get_username_field(self):
                return TextInputComponent(self.find_child(By.NAME, 'username'))

            def login(self, username, password):
                self.get_username_field().enter_text(username)
                self.get_password_field().enter_text(password)
                self.get_submit_button().click()
    """

    def __init__(self, root: WebElement):
        """
        Initialize component with root element.

        Args:
            root: The WebElement that serves as the component's root
        """
        self._root = root

    @property
    def root(self) -> WebElement:
        """The root WebElement of this component."""
        return self._root

    @property
    def driver(self) -> WebDriver:
        """Get the WebDriver from the root element."""
        return self._root.parent

    # State queries
    def is_displayed(self) -> bool:
        """Check if the component is displayed."""
        try:
            return self._root.is_displayed()
        except StaleElementReferenceException:
            return False

    def is_enabled(self) -> bool:
        """Check if the component is enabled."""
        return self._root.is_enabled()

    def is_selected(self) -> bool:
        """Check if the component is selected (for checkboxes, radio buttons)."""
        return self._root.is_selected()

    # Element properties
    @property
    def tag_name(self) -> str:
        """Get the tag name of the root element."""
        return self._root.tag_name

    @property
    def text(self) -> str:
        """Get the visible text of the component."""
        return self._root.text

    def get_attribute(self, name: str) -> Optional[str]:
        """Get an attribute value from the root element."""
        return self._root.get_attribute(name)

    def get_css_value(self, property_name: str) -> str:
        """Get a CSS property value."""
        return self._root.value_of_css_property(property_name)

    # Geometry
    @property
    def location(self) -> dict:
        """Get the location of the component."""
        return self._root.location

    @property
    def size(self) -> dict:
        """Get the size of the component."""
        return self._root.size

    @property
    def rect(self) -> dict:
        """Get the bounding rectangle of the component."""
        return self._root.rect

    # Scoped element finding
    def find_child(self, by: By, value: str) -> WebElement:
        """Find a child element within this component."""
        return self._root.find_element(by, value)

    def find_children(self, by: By, value: str) -> List[WebElement]:
        """Find all matching child elements within this component."""
        return self._root.find_elements(by, value)

    def child_exists(self, by: By, value: str) -> bool:
        """Check if a child element exists."""
        try:
            self.find_child(by, value)
            return True
        except NoSuchElementException:
            return False

    # Shadow DOM
    @property
    def shadow_root(self):
        """Get the shadow root if this is a shadow host."""
        return self._root.shadow_root

    def find_in_shadow(self, by: By, value: str) -> WebElement:
        """Find an element within the shadow DOM."""
        return self.shadow_root.find_element(by, value)

    # Actions
    def click(self) -> None:
        """Click the component."""
        self._root.click()

    def scroll_into_view(self) -> None:
        """Scroll the component into view."""
        self.driver.execute_script(
            "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'})",
            self._root
        )

    def screenshot(self, filename: str) -> bool:
        """Take a screenshot of this component."""
        return self._root.screenshot(filename)

    def __repr__(self) -> str:
        try:
            return f"{self.__class__.__name__}(<{self.tag_name}>)"
        except StaleElementReferenceException:
            return f"{self.__class__.__name__}(<stale>)"


class BasePage(ABC):
    """
    Base class for Page Objects.

    Pages encapsulate a full page/view and provide access to components.

    Example:
        class SettingsPage(BasePage):
            @property
            def url_pattern(self):
                return '/settings'

            def wait_for_page_load(self):
                self.wait.until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, '.settings-container')
                ))

            def get_theme_selector(self):
                return SelectComponent(
                    self.driver.find_element(By.ID, 'theme-select')
                )
    """

    def __init__(self, driver: WebDriver, timeout: float = 10.0):
        """
        Initialize page object.

        Args:
            driver: WebDriver instance
            timeout: Default wait timeout in seconds
        """
        self._driver = driver
        self._wait = WebDriverWait(driver, timeout)
        self.wait_for_page_load()

    @property
    def driver(self) -> WebDriver:
        """The WebDriver instance."""
        return self._driver

    @property
    def wait(self) -> WebDriverWait:
        """The default WebDriverWait instance."""
        return self._wait

    @property
    @abstractmethod
    def url_pattern(self) -> str:
        """URL pattern for this page."""
        pass

    @abstractmethod
    def wait_for_page_load(self) -> None:
        """Wait for the page to be fully loaded."""
        pass

    @property
    def title(self) -> str:
        """Get the page title."""
        return self._driver.title

    @property
    def current_url(self) -> str:
        """Get the current URL."""
        return self._driver.current_url

    def refresh(self) -> None:
        """Refresh the page."""
        self._driver.refresh()
        self.wait_for_page_load()


# ============================================================================
# ActionDelegate: Form Components
# ============================================================================

class TextInputComponent(BaseComponent):
    """
    Text input field component.

    Handles text entry, clearing, and validation for input/textarea elements.
    """

    @property
    def value(self) -> str:
        """Get the current value of the input."""
        return self.get_attribute('value') or ''

    def enter_text(self, text: str, clear_first: bool = True) -> None:
        """
        Enter text into the input.

        Args:
            text: Text to enter
            clear_first: Whether to clear existing text first
        """
        if clear_first:
            self.clear()
        self._root.send_keys(text)

    def clear(self) -> None:
        """Clear the input field."""
        self._root.clear()

    def send_keys(self, *keys) -> None:
        """Send keys to the input (for special keys like ENTER)."""
        self._root.send_keys(*keys)

    @property
    def placeholder(self) -> Optional[str]:
        """Get the placeholder text."""
        return self.get_attribute('placeholder')

    @property
    def is_readonly(self) -> bool:
        """Check if the input is read-only."""
        return self.get_attribute('readonly') is not None

    @property
    def validation_message(self) -> str:
        """Get the browser validation message."""
        return self.get_attribute('validationMessage') or ''

    def has_validation_error(self) -> bool:
        """Check if there's a validation error."""
        return bool(self.validation_message)


class SelectComponent(BaseComponent):
    """
    Select/dropdown component.

    Wraps Selenium's Select class with component pattern.
    """

    def __init__(self, root: WebElement):
        super().__init__(root)
        self._select = Select(root)

    @property
    def selected_option(self) -> str:
        """Get the currently selected option text."""
        return self._select.first_selected_option.text

    @property
    def selected_value(self) -> str:
        """Get the currently selected option value."""
        return self._select.first_selected_option.get_attribute('value')

    @property
    def options(self) -> List[str]:
        """Get all option texts."""
        return [opt.text for opt in self._select.options]

    @property
    def option_values(self) -> List[str]:
        """Get all option values."""
        return [opt.get_attribute('value') for opt in self._select.options]

    def select_by_text(self, text: str) -> None:
        """Select option by visible text."""
        self._select.select_by_visible_text(text)

    def select_by_value(self, value: str) -> None:
        """Select option by value attribute."""
        self._select.select_by_value(value)

    def select_by_index(self, index: int) -> None:
        """Select option by index."""
        self._select.select_by_index(index)

    @property
    def is_multiple(self) -> bool:
        """Check if this is a multi-select."""
        return self._select.is_multiple


class CheckboxComponent(BaseComponent):
    """
    Checkbox input component.
    """

    @property
    def is_checked(self) -> bool:
        """Check if the checkbox is checked."""
        return self._root.is_selected()

    def check(self) -> None:
        """Ensure the checkbox is checked."""
        if not self.is_checked:
            self.click()

    def uncheck(self) -> None:
        """Ensure the checkbox is unchecked."""
        if self.is_checked:
            self.click()

    def toggle(self) -> None:
        """Toggle the checkbox state."""
        self.click()

    def set(self, checked: bool) -> None:
        """Set the checkbox to a specific state."""
        if checked:
            self.check()
        else:
            self.uncheck()


class RadioGroupComponent(BaseComponent):
    """
    Radio button group component.

    Manages a group of radio buttons with the same name.
    """

    def __init__(self, root: WebElement, name: str):
        """
        Initialize radio group.

        Args:
            root: Container element holding the radio buttons
            name: The name attribute of the radio buttons
        """
        super().__init__(root)
        self._name = name

    @property
    def options(self) -> List[WebElement]:
        """Get all radio button elements."""
        return self.find_children(By.CSS_SELECTOR, f'input[type="radio"][name="{self._name}"]')

    @property
    def selected_value(self) -> Optional[str]:
        """Get the value of the selected radio button."""
        for option in self.options:
            if option.is_selected():
                return option.get_attribute('value')
        return None

    def select_by_value(self, value: str) -> None:
        """Select a radio button by its value."""
        for option in self.options:
            if option.get_attribute('value') == value:
                option.click()
                return
        raise ValueError(f"No radio option with value: {value}")


class ButtonComponent(BaseComponent):
    """
    Button component.

    Handles button elements with loading/disabled states.
    """

    @property
    def button_text(self) -> str:
        """Get the button text."""
        return self.text.strip()

    @property
    def is_loading(self) -> bool:
        """Check if the button is in a loading state."""
        # Common patterns for loading state
        classes = self.get_attribute('class') or ''
        aria_busy = self.get_attribute('aria-busy')
        return (
            'loading' in classes.lower() or
            'spinner' in classes.lower() or
            aria_busy == 'true'
        )

    def click_and_wait(self, condition, timeout: float = 10.0) -> None:
        """Click and wait for a condition."""
        self.click()
        WebDriverWait(self.driver, timeout).until(condition)

    def submit(self) -> None:
        """Submit the form containing this button."""
        self._root.submit()


class FileUploadComponent(BaseComponent):
    """
    File upload input component.
    """

    def upload(self, file_path: str) -> None:
        """
        Upload a file.

        Args:
            file_path: Absolute path to the file
        """
        self._root.send_keys(file_path)

    def upload_multiple(self, file_paths: List[str]) -> None:
        """Upload multiple files (if supported)."""
        if not self.accepts_multiple:
            raise ValueError("This input doesn't accept multiple files")
        self._root.send_keys('\n'.join(file_paths))

    @property
    def accepts_multiple(self) -> bool:
        """Check if multiple files can be uploaded."""
        return self.get_attribute('multiple') is not None

    @property
    def accepted_types(self) -> Optional[str]:
        """Get accepted file types."""
        return self.get_attribute('accept')


# ============================================================================
# NavDelegate: Navigation Components
# ============================================================================

class LinkComponent(BaseComponent):
    """
    Anchor/link component.
    """

    @property
    def href(self) -> Optional[str]:
        """Get the link URL."""
        return self.get_attribute('href')

    @property
    def is_active(self) -> bool:
        """Check if this is the current page link."""
        aria_current = self.get_attribute('aria-current')
        classes = self.get_attribute('class') or ''
        return (
            aria_current == 'page' or
            'active' in classes.lower() or
            'current' in classes.lower()
        )

    @property
    def opens_new_tab(self) -> bool:
        """Check if link opens in new tab."""
        target = self.get_attribute('target')
        return target == '_blank'


class MenuComponent(BaseComponent):
    """
    Navigation menu component.
    """

    def __init__(self, root: WebElement, item_selector: str = '[role="menuitem"], li > a'):
        super().__init__(root)
        self._item_selector = item_selector

    @property
    def items(self) -> List[LinkComponent]:
        """Get all menu items as LinkComponents."""
        elements = self.find_children(By.CSS_SELECTOR, self._item_selector)
        return [LinkComponent(el) for el in elements]

    @property
    def item_texts(self) -> List[str]:
        """Get text of all menu items."""
        return [item.text for item in self.items]

    def get_item(self, text: str) -> Optional[LinkComponent]:
        """Get a menu item by its text."""
        for item in self.items:
            if item.text.strip() == text:
                return item
        return None

    def navigate_to(self, item_text: str) -> None:
        """Click a menu item by its text."""
        item = self.get_item(item_text)
        if item:
            item.click()
        else:
            raise ValueError(f"Menu item not found: {item_text}")

    @property
    def active_item(self) -> Optional[LinkComponent]:
        """Get the currently active menu item."""
        for item in self.items:
            if item.is_active:
                return item
        return None


class TabsComponent(BaseComponent):
    """
    Tab navigation component.
    """

    @property
    def tabs(self) -> List[WebElement]:
        """Get all tab elements."""
        return self.find_children(By.CSS_SELECTOR, '[role="tab"]')

    @property
    def tab_names(self) -> List[str]:
        """Get names of all tabs."""
        return [tab.text for tab in self.tabs]

    @property
    def active_tab(self) -> Optional[str]:
        """Get the name of the active tab."""
        for tab in self.tabs:
            if tab.get_attribute('aria-selected') == 'true':
                return tab.text
        return None

    def select_tab(self, name: str) -> None:
        """Select a tab by name."""
        for tab in self.tabs:
            if tab.text == name:
                tab.click()
                return
        raise ValueError(f"Tab not found: {name}")

    @property
    def active_panel(self) -> Optional[WebElement]:
        """Get the currently active tab panel."""
        for tab in self.tabs:
            if tab.get_attribute('aria-selected') == 'true':
                panel_id = tab.get_attribute('aria-controls')
                if panel_id:
                    return self.driver.find_element(By.ID, panel_id)
        return None


class PaginationComponent(BaseComponent):
    """
    Pagination navigation component.
    """

    @property
    def current_page(self) -> int:
        """Get the current page number."""
        current = self.find_child(By.CSS_SELECTOR, '[aria-current="page"], .active, .current')
        return int(current.text)

    @property
    def total_pages(self) -> Optional[int]:
        """Get total number of pages if available."""
        try:
            # Try common patterns
            page_links = self.find_children(By.CSS_SELECTOR, 'a[href*="page"], button')
            numbers = []
            for link in page_links:
                try:
                    numbers.append(int(link.text))
                except ValueError:
                    continue
            return max(numbers) if numbers else None
        except NoSuchElementException:
            return None

    def go_to_page(self, page: int) -> None:
        """Navigate to a specific page."""
        link = self.find_child(By.XPATH, f".//a[text()='{page}'] | .//button[text()='{page}']")
        link.click()

    def next_page(self) -> None:
        """Go to the next page."""
        self.find_child(By.CSS_SELECTOR, '[rel="next"], [aria-label*="next"], .next').click()

    def previous_page(self) -> None:
        """Go to the previous page."""
        self.find_child(By.CSS_SELECTOR, '[rel="prev"], [aria-label*="prev"], .prev').click()

    @property
    def has_next(self) -> bool:
        """Check if there's a next page."""
        try:
            next_btn = self.find_child(By.CSS_SELECTOR, '[rel="next"], [aria-label*="next"], .next')
            return next_btn.is_enabled()
        except NoSuchElementException:
            return False

    @property
    def has_previous(self) -> bool:
        """Check if there's a previous page."""
        try:
            prev_btn = self.find_child(By.CSS_SELECTOR, '[rel="prev"], [aria-label*="prev"], .prev')
            return prev_btn.is_enabled()
        except NoSuchElementException:
            return False


class ModalComponent(BaseComponent):
    """
    Modal/dialog component.
    """

    @property
    def is_open(self) -> bool:
        """Check if the modal is open."""
        return self.is_displayed()

    @property
    def title(self) -> Optional[str]:
        """Get the modal title."""
        try:
            title_el = self.find_child(By.CSS_SELECTOR, '[role="heading"], .modal-title, h1, h2')
            return title_el.text
        except NoSuchElementException:
            return None

    def close(self) -> None:
        """Close the modal."""
        try:
            close_btn = self.find_child(By.CSS_SELECTOR,
                '[aria-label*="close"], [aria-label*="Close"], .close, .modal-close')
            close_btn.click()
        except NoSuchElementException:
            # Try pressing Escape
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()

    def confirm(self) -> None:
        """Click the confirm/OK button."""
        self.find_child(By.CSS_SELECTOR,
            'button[type="submit"], .confirm, .ok, [data-action="confirm"]').click()

    def cancel(self) -> None:
        """Click the cancel button."""
        self.find_child(By.CSS_SELECTOR, '.cancel, [data-action="cancel"]').click()


class SearchComponent(BaseComponent):
    """
    Search input with suggestions/autocomplete.
    """

    def __init__(self, root: WebElement, input_selector: str = 'input[type="search"], input'):
        super().__init__(root)
        self._input_selector = input_selector

    @property
    def input(self) -> TextInputComponent:
        """Get the search input."""
        return TextInputComponent(self.find_child(By.CSS_SELECTOR, self._input_selector))

    def search(self, query: str, submit: bool = True) -> None:
        """
        Perform a search.

        Args:
            query: Search query
            submit: Whether to press Enter after typing
        """
        self.input.enter_text(query)
        if submit:
            self.input.send_keys(Keys.ENTER)

    @property
    def suggestions(self) -> List[str]:
        """Get autocomplete suggestions if visible."""
        try:
            items = self.find_children(By.CSS_SELECTOR,
                '[role="option"], .suggestion, .autocomplete-item')
            return [item.text for item in items]
        except NoSuchElementException:
            return []

    def select_suggestion(self, text: str) -> None:
        """Select a suggestion by text."""
        items = self.find_children(By.CSS_SELECTOR,
            '[role="option"], .suggestion, .autocomplete-item')
        for item in items:
            if item.text == text:
                item.click()
                return
        raise ValueError(f"Suggestion not found: {text}")


# ============================================================================
# Component Factory and Recognition
# ============================================================================

class ComponentFactory:
    """
    Factory for creating components from WebElements.

    Recognizes component types based on element characteristics.
    """

    @staticmethod
    def from_element(element: WebElement) -> BaseComponent:
        """
        Create an appropriate component from a WebElement.

        Args:
            element: The WebElement to wrap

        Returns:
            A component appropriate for the element type
        """
        tag = element.tag_name.lower()
        element_type = element.get_attribute('type') or ''
        role = element.get_attribute('role') or ''

        # Form elements
        if tag == 'input':
            if element_type in ('checkbox',):
                return CheckboxComponent(element)
            elif element_type in ('file',):
                return FileUploadComponent(element)
            else:
                return TextInputComponent(element)
        elif tag == 'select':
            return SelectComponent(element)
        elif tag == 'textarea':
            return TextInputComponent(element)
        elif tag == 'button' or element_type == 'submit':
            return ButtonComponent(element)

        # Navigation elements
        elif tag == 'a':
            return LinkComponent(element)
        elif role == 'tablist':
            return TabsComponent(element)
        elif role == 'menu' or role == 'menubar':
            return MenuComponent(element)
        elif role == 'dialog' or role == 'alertdialog':
            return ModalComponent(element)

        # Default
        return BaseComponent(element)


# ============================================================================
# Wait Utilities
# ============================================================================

class ComponentWait:
    """
    Wait utilities for components.
    """

    def __init__(self, driver: WebDriver, timeout: float = 10.0):
        self._driver = driver
        self._timeout = timeout
        self._wait = WebDriverWait(driver, timeout)

    def until_visible(self, locator: tuple) -> WebElement:
        """Wait until element is visible."""
        return self._wait.until(EC.visibility_of_element_located(locator))

    def until_clickable(self, locator: tuple) -> WebElement:
        """Wait until element is clickable."""
        return self._wait.until(EC.element_to_be_clickable(locator))

    def until_present(self, locator: tuple) -> WebElement:
        """Wait until element is present in DOM."""
        return self._wait.until(EC.presence_of_element_located(locator))

    def until_invisible(self, locator: tuple) -> bool:
        """Wait until element is not visible."""
        return self._wait.until(EC.invisibility_of_element_located(locator))

    def until_text_present(self, locator: tuple, text: str) -> bool:
        """Wait until element contains text."""
        return self._wait.until(EC.text_to_be_present_in_element(locator, text))

    def until_component(self, locator: tuple) -> BaseComponent:
        """Wait for element and return as component."""
        element = self.until_visible(locator)
        return ComponentFactory.from_element(element)
