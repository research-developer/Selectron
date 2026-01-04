"""
Selectron POM Loader

Dynamic Page Object Model loader that reads JSON definitions and generates
methods at runtime. Makes POMs portable, testable, and framework-agnostic.

Usage:
    from selectron.pom_loader import POMLoader, BasePOM

    # Load a POM from JSON files
    pom = POMLoader.load('Claude', driver)
    pom.create_new_chat()

    # Or in iPython for interactive testing
    loader = POMLoader('/path/to/poms/Claude')
    elements = loader.elements
    operations = loader.operations
"""

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
from dataclasses import dataclass, field, asdict
from enum import Enum

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException


class SelectorType(str, Enum):
    """Supported selector types."""
    CSS = "css"
    XPATH = "xpath"
    ID = "id"
    NAME = "name"
    CLASS_NAME = "class_name"
    TAG_NAME = "tag_name"
    LINK_TEXT = "link_text"
    PARTIAL_LINK_TEXT = "partial_link_text"
    ARIA_LABEL = "aria_label"  # Convenience: translates to CSS [aria-label="..."]


class CRUDType(str, Enum):
    """CRUD operation types."""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    NAVIGATE = "navigate"
    UNKNOWN = "unknown"


class ActionType(str, Enum):
    """Supported action types."""
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    TYPE = "type"
    CLEAR = "clear"
    CLEAR_AND_TYPE = "clear_and_type"
    SEND_KEYS = "send_keys"
    SHORTCUT = "shortcut"
    HOVER = "hover"
    SCROLL_INTO_VIEW = "scroll_into_view"
    GET_TEXT = "get_text"
    GET_ATTRIBUTE = "get_attribute"
    WAIT_VISIBLE = "wait_visible"
    WAIT_CLICKABLE = "wait_clickable"
    WAIT_INVISIBLE = "wait_invisible"
    CUSTOM = "custom"


class ComponentType(str, Enum):
    """Component types."""
    BUTTON = "Button"
    LINK = "Link"
    TEXT_INPUT = "TextInput"
    TEXT_AREA = "TextArea"
    SELECT = "Select"
    CHECKBOX = "Checkbox"
    RADIO = "Radio"
    TAB = "Tab"
    MODAL = "Modal"
    MENU = "Menu"
    ELEMENT = "Element"


@dataclass
class Selector:
    """Element selector definition."""
    type: str
    value: str

    def to_selenium(self) -> tuple:
        """Convert to Selenium By locator tuple."""
        mapping = {
            SelectorType.CSS.value: By.CSS_SELECTOR,
            SelectorType.XPATH.value: By.XPATH,
            SelectorType.ID.value: By.ID,
            SelectorType.NAME.value: By.NAME,
            SelectorType.CLASS_NAME.value: By.CLASS_NAME,
            SelectorType.TAG_NAME.value: By.TAG_NAME,
            SelectorType.LINK_TEXT.value: By.LINK_TEXT,
            SelectorType.PARTIAL_LINK_TEXT.value: By.PARTIAL_LINK_TEXT,
        }

        # Handle aria_label convenience type
        if self.type == SelectorType.ARIA_LABEL.value:
            return (By.CSS_SELECTOR, f'[aria-label="{self.value}"]')

        by_type = mapping.get(self.type, By.CSS_SELECTOR)
        return (by_type, self.value)


@dataclass
class ElementDef:
    """Element definition from JSON."""
    id: str
    selector: Selector
    crud_type: str = CRUDType.UNKNOWN.value
    component_type: str = ComponentType.ELEMENT.value
    text: str = ""
    aria_label: str = ""
    confidence: float = 0.0
    alt_selectors: List[Selector] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> 'ElementDef':
        """Create from dictionary."""
        selector_data = data.get('selector', {})
        selector = Selector(
            type=selector_data.get('type', 'css'),
            value=selector_data.get('value', '')
        )

        alt_selectors = []
        for alt in data.get('alt_selectors', []):
            alt_selectors.append(Selector(type=alt.get('type', 'css'), value=alt.get('value', '')))

        return cls(
            id=data.get('id', ''),
            selector=selector,
            crud_type=data.get('crud_type', CRUDType.UNKNOWN.value),
            component_type=data.get('component_type', ComponentType.ELEMENT.value),
            text=data.get('text', ''),
            aria_label=data.get('aria_label', ''),
            confidence=data.get('confidence', 0.0),
            alt_selectors=alt_selectors,
            metadata=data.get('metadata', {})
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'selector': {'type': self.selector.type, 'value': self.selector.value},
            'crud_type': self.crud_type,
            'component_type': self.component_type,
            'text': self.text,
            'aria_label': self.aria_label,
            'confidence': self.confidence,
            'alt_selectors': [{'type': s.type, 'value': s.value} for s in self.alt_selectors],
            'metadata': self.metadata
        }


@dataclass
class OperationDef:
    """Operation definition from JSON."""
    name: str
    element_id: str
    action: str
    description: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    pre_condition: str = ""  # Lambda string to evaluate
    post_condition: str = ""  # Lambda string to evaluate
    wait_after: float = 0.0  # Seconds to wait after operation
    shortcut_keys: List[str] = field(default_factory=list)  # For keyboard shortcuts

    @classmethod
    def from_dict(cls, data: dict) -> 'OperationDef':
        """Create from dictionary."""
        return cls(
            name=data.get('name', ''),
            element_id=data.get('element_id', ''),
            action=data.get('action', ActionType.CLICK.value),
            description=data.get('description', ''),
            params=data.get('params', {}),
            pre_condition=data.get('pre_condition', ''),
            post_condition=data.get('post_condition', ''),
            wait_after=data.get('wait_after', 0.0),
            shortcut_keys=data.get('shortcut_keys', [])
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'name': self.name,
            'element_id': self.element_id,
            'action': self.action,
            'description': self.description,
            'params': self.params,
            'pre_condition': self.pre_condition,
            'post_condition': self.post_condition,
            'wait_after': self.wait_after,
            'shortcut_keys': self.shortcut_keys
        }


class POMData:
    """Container for loaded POM data."""

    def __init__(self, app_name: str, pom_path: Path):
        self.app_name = app_name
        self.pom_path = pom_path
        self.elements: Dict[str, ElementDef] = {}
        self.operations: Dict[str, OperationDef] = {}
        self.metadata: Dict[str, Any] = {}

    def load(self) -> 'POMData':
        """Load elements and operations from JSON files."""
        elements_path = self.pom_path / 'elements.json'
        operations_path = self.pom_path / 'operations.json'

        # Load elements
        if elements_path.exists():
            with open(elements_path, 'r') as f:
                data = json.load(f)
                self.metadata = {k: v for k, v in data.items() if k != 'elements'}
                for elem_data in data.get('elements', []):
                    elem = ElementDef.from_dict(elem_data)
                    self.elements[elem.id] = elem

        # Load operations
        if operations_path.exists():
            with open(operations_path, 'r') as f:
                data = json.load(f)
                for op_data in data.get('operations', []):
                    op = OperationDef.from_dict(op_data)
                    self.operations[op.name] = op

        return self

    def save(self) -> None:
        """Save elements and operations to JSON files."""
        self.pom_path.mkdir(parents=True, exist_ok=True)

        # Save elements
        elements_data = {
            'app_name': self.app_name,
            **self.metadata,
            'elements': [elem.to_dict() for elem in self.elements.values()]
        }
        with open(self.pom_path / 'elements.json', 'w') as f:
            json.dump(elements_data, f, indent=2)

        # Save operations
        operations_data = {
            'app_name': self.app_name,
            'operations': [op.to_dict() for op in self.operations.values()]
        }
        with open(self.pom_path / 'operations.json', 'w') as f:
            json.dump(operations_data, f, indent=2)

    def get_element(self, element_id: str) -> Optional[ElementDef]:
        """Get element by ID."""
        return self.elements.get(element_id)

    def get_operation(self, name: str) -> Optional[OperationDef]:
        """Get operation by name."""
        return self.operations.get(name)

    def get_elements_by_crud(self, crud_type: str) -> List[ElementDef]:
        """Get all elements of a specific CRUD type."""
        return [e for e in self.elements.values() if e.crud_type == crud_type]


class BasePOM:
    """
    Base class for JSON-loaded Page Object Models.

    Provides dynamic method generation based on loaded operations.
    """

    def __init__(self, driver: WebDriver, pom_data: POMData, timeout: float = 10.0):
        self._driver = driver
        self._pom_data = pom_data
        self._timeout = timeout
        self._wait = WebDriverWait(driver, timeout)
        self._action_handlers = self._build_action_handlers()

        # Generate methods for each operation
        self._generate_methods()

    @property
    def driver(self) -> WebDriver:
        return self._driver

    @property
    def elements(self) -> Dict[str, ElementDef]:
        return self._pom_data.elements

    @property
    def operations(self) -> Dict[str, OperationDef]:
        return self._pom_data.operations

    @property
    def app_name(self) -> str:
        return self._pom_data.app_name

    def _build_action_handlers(self) -> Dict[str, Callable]:
        """Build action handler mapping."""
        return {
            ActionType.CLICK.value: self._action_click,
            ActionType.DOUBLE_CLICK.value: self._action_double_click,
            ActionType.RIGHT_CLICK.value: self._action_right_click,
            ActionType.TYPE.value: self._action_type,
            ActionType.CLEAR.value: self._action_clear,
            ActionType.CLEAR_AND_TYPE.value: self._action_clear_and_type,
            ActionType.SEND_KEYS.value: self._action_send_keys,
            ActionType.SHORTCUT.value: self._action_shortcut,
            ActionType.HOVER.value: self._action_hover,
            ActionType.SCROLL_INTO_VIEW.value: self._action_scroll_into_view,
            ActionType.GET_TEXT.value: self._action_get_text,
            ActionType.GET_ATTRIBUTE.value: self._action_get_attribute,
            ActionType.WAIT_VISIBLE.value: self._action_wait_visible,
            ActionType.WAIT_CLICKABLE.value: self._action_wait_clickable,
            ActionType.WAIT_INVISIBLE.value: self._action_wait_invisible,
        }

    def find_element(self, element_id: str) -> Optional[WebElement]:
        """Find an element by its ID from the POM data."""
        elem_def = self._pom_data.get_element(element_id)
        if not elem_def:
            return None

        try:
            return self._driver.find_element(*elem_def.selector.to_selenium())
        except NoSuchElementException:
            # Try alternate selectors
            for alt in elem_def.alt_selectors:
                try:
                    return self._driver.find_element(*alt.to_selenium())
                except NoSuchElementException:
                    continue
        return None

    def find_elements(self, element_id: str) -> List[WebElement]:
        """Find all elements matching an element ID from the POM data."""
        elem_def = self._pom_data.get_element(element_id)
        if not elem_def:
            return []

        return self._driver.find_elements(*elem_def.selector.to_selenium())

    def execute_operation(self, name: str, **kwargs) -> Any:
        """Execute an operation by name."""
        op = self._pom_data.get_operation(name)
        if not op:
            raise ValueError(f"Operation not found: {name}")

        # Check pre-condition if defined
        if op.pre_condition:
            if not self._eval_condition(op.pre_condition):
                raise RuntimeError(f"Pre-condition failed for {name}")

        # Get element (if not a shortcut operation)
        element = None
        if op.element_id and op.action != ActionType.SHORTCUT.value:
            element = self.find_element(op.element_id)
            if not element and op.action not in [ActionType.SHORTCUT.value]:
                raise NoSuchElementException(f"Element not found: {op.element_id}")

        # Merge params with kwargs
        params = {**op.params, **kwargs}

        # Execute action
        handler = self._action_handlers.get(op.action)
        if handler:
            result = handler(element, op, **params)
        else:
            raise ValueError(f"Unknown action type: {op.action}")

        # Wait after if specified
        if op.wait_after > 0:
            import time
            time.sleep(op.wait_after)

        # Check post-condition if defined
        if op.post_condition:
            if not self._eval_condition(op.post_condition):
                raise RuntimeError(f"Post-condition failed for {name}")

        return result

    def _eval_condition(self, condition: str) -> bool:
        """Evaluate a condition string (lambda)."""
        try:
            # Safety: only allow specific variables
            safe_globals = {
                'driver': self._driver,
                'By': By,
                'EC': EC,
                'Keys': Keys,
            }
            func = eval(condition, safe_globals)
            return bool(func(self._driver))
        except Exception:
            return False

    def _generate_methods(self) -> None:
        """Dynamically generate methods for each operation."""
        for op_name, op_def in self._pom_data.operations.items():
            # Create method
            def make_method(operation_name: str):
                def method(**kwargs):
                    return self.execute_operation(operation_name, **kwargs)
                method.__name__ = operation_name
                method.__doc__ = op_def.description or f"Execute {operation_name} operation"
                return method

            setattr(self, op_name, make_method(op_name))

    # Action handlers
    def _action_click(self, element: WebElement, op: OperationDef, **kwargs) -> None:
        element.click()

    def _action_double_click(self, element: WebElement, op: OperationDef, **kwargs) -> None:
        ActionChains(self._driver).double_click(element).perform()

    def _action_right_click(self, element: WebElement, op: OperationDef, **kwargs) -> None:
        ActionChains(self._driver).context_click(element).perform()

    def _action_type(self, element: WebElement, op: OperationDef, text: str = "", **kwargs) -> None:
        element.send_keys(text)

    def _action_clear(self, element: WebElement, op: OperationDef, **kwargs) -> None:
        element.clear()

    def _action_clear_and_type(self, element: WebElement, op: OperationDef, text: str = "", **kwargs) -> None:
        element.clear()
        element.send_keys(text)

    def _action_send_keys(self, element: WebElement, op: OperationDef, keys: str = "", **kwargs) -> None:
        """Send special keys. Keys string can include KEY_NAME references."""
        key_map = {
            'ENTER': Keys.ENTER,
            'TAB': Keys.TAB,
            'ESCAPE': Keys.ESCAPE,
            'BACKSPACE': Keys.BACKSPACE,
            'DELETE': Keys.DELETE,
            'ARROW_UP': Keys.ARROW_UP,
            'ARROW_DOWN': Keys.ARROW_DOWN,
            'ARROW_LEFT': Keys.ARROW_LEFT,
            'ARROW_RIGHT': Keys.ARROW_RIGHT,
            'COMMAND': Keys.COMMAND,
            'CONTROL': Keys.CONTROL,
            'ALT': Keys.ALT,
            'SHIFT': Keys.SHIFT,
        }
        resolved_keys = key_map.get(keys.upper(), keys)
        if element:
            element.send_keys(resolved_keys)
        else:
            ActionChains(self._driver).send_keys(resolved_keys).perform()

    def _action_shortcut(self, element: WebElement, op: OperationDef, **kwargs) -> None:
        """Execute a keyboard shortcut from shortcut_keys."""
        if not op.shortcut_keys:
            return

        key_map = {
            'COMMAND': Keys.COMMAND,
            'CMD': Keys.COMMAND,
            'CONTROL': Keys.CONTROL,
            'CTRL': Keys.CONTROL,
            'ALT': Keys.ALT,
            'OPTION': Keys.ALT,
            'SHIFT': Keys.SHIFT,
            'ENTER': Keys.ENTER,
            'TAB': Keys.TAB,
            'ESCAPE': Keys.ESCAPE,
            'ESC': Keys.ESCAPE,
        }

        actions = ActionChains(self._driver)
        modifiers = []
        final_key = None

        for key in op.shortcut_keys:
            mapped = key_map.get(key.upper())
            if mapped and key.upper() in ['COMMAND', 'CMD', 'CONTROL', 'CTRL', 'ALT', 'OPTION', 'SHIFT']:
                modifiers.append(mapped)
            else:
                final_key = mapped or key

        # Press modifiers
        for mod in modifiers:
            actions.key_down(mod)

        # Press final key
        if final_key:
            actions.send_keys(final_key)

        # Release modifiers in reverse
        for mod in reversed(modifiers):
            actions.key_up(mod)

        actions.perform()

    def _action_hover(self, element: WebElement, op: OperationDef, **kwargs) -> None:
        ActionChains(self._driver).move_to_element(element).perform()

    def _action_scroll_into_view(self, element: WebElement, op: OperationDef, **kwargs) -> None:
        self._driver.execute_script(
            "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'})",
            element
        )

    def _action_get_text(self, element: WebElement, op: OperationDef, **kwargs) -> str:
        return element.text

    def _action_get_attribute(self, element: WebElement, op: OperationDef, attribute: str = "value", **kwargs) -> str:
        return element.get_attribute(attribute) or ""

    def _action_wait_visible(self, element: WebElement, op: OperationDef, timeout: float = None, **kwargs) -> WebElement:
        elem_def = self._pom_data.get_element(op.element_id)
        wait = WebDriverWait(self._driver, timeout or self._timeout)
        return wait.until(EC.visibility_of_element_located(elem_def.selector.to_selenium()))

    def _action_wait_clickable(self, element: WebElement, op: OperationDef, timeout: float = None, **kwargs) -> WebElement:
        elem_def = self._pom_data.get_element(op.element_id)
        wait = WebDriverWait(self._driver, timeout or self._timeout)
        return wait.until(EC.element_to_be_clickable(elem_def.selector.to_selenium()))

    def _action_wait_invisible(self, element: WebElement, op: OperationDef, timeout: float = None, **kwargs) -> bool:
        elem_def = self._pom_data.get_element(op.element_id)
        wait = WebDriverWait(self._driver, timeout or self._timeout)
        return wait.until(EC.invisibility_of_element_located(elem_def.selector.to_selenium()))

    def screenshot(self, filename: str) -> bool:
        """Take a screenshot."""
        return self._driver.save_screenshot(filename)


class POMLoader:
    """
    Factory for loading POMs from JSON.

    Usage:
        # Load from poms directory
        pom = POMLoader.load('Claude', driver)

        # Or specify path
        pom = POMLoader.load_from_path('/path/to/pom', driver)

        # Just load data without driver (for inspection)
        data = POMLoader.load_data('Claude')
    """

    # Default poms directory (relative to this file)
    DEFAULT_POMS_DIR = Path(__file__).parent.parent / 'poms'

    @classmethod
    def load(cls, app_name: str, driver: WebDriver,
             poms_dir: Optional[Path] = None, timeout: float = 10.0) -> BasePOM:
        """
        Load a POM by app name.

        Args:
            app_name: Name of the app (e.g., 'Claude', 'Obsidian')
            driver: WebDriver instance
            poms_dir: Directory containing POM folders (default: poms/)
            timeout: Default timeout for waits

        Returns:
            BasePOM instance with dynamically generated methods
        """
        poms_dir = poms_dir or cls.DEFAULT_POMS_DIR
        pom_path = poms_dir / app_name

        if not pom_path.exists():
            raise FileNotFoundError(f"POM not found: {pom_path}")

        data = POMData(app_name, pom_path).load()
        return BasePOM(driver, data, timeout)

    @classmethod
    def load_from_path(cls, pom_path: Union[str, Path], driver: WebDriver,
                       timeout: float = 10.0) -> BasePOM:
        """
        Load a POM from a specific path.

        Args:
            pom_path: Path to the POM directory
            driver: WebDriver instance
            timeout: Default timeout for waits

        Returns:
            BasePOM instance
        """
        pom_path = Path(pom_path)
        app_name = pom_path.name
        data = POMData(app_name, pom_path).load()
        return BasePOM(driver, data, timeout)

    @classmethod
    def load_data(cls, app_name: str, poms_dir: Optional[Path] = None) -> POMData:
        """
        Load just the POM data without a driver (for inspection/testing).

        Args:
            app_name: Name of the app
            poms_dir: Directory containing POM folders

        Returns:
            POMData instance
        """
        poms_dir = poms_dir or cls.DEFAULT_POMS_DIR
        pom_path = poms_dir / app_name
        return POMData(app_name, pom_path).load()

    @classmethod
    def create_pom(cls, app_name: str, poms_dir: Optional[Path] = None) -> POMData:
        """
        Create a new empty POM data structure.

        Args:
            app_name: Name of the app
            poms_dir: Directory to create POM in

        Returns:
            Empty POMData instance (call .save() to persist)
        """
        poms_dir = poms_dir or cls.DEFAULT_POMS_DIR
        pom_path = poms_dir / app_name
        return POMData(app_name, pom_path)

    @classmethod
    def list_poms(cls, poms_dir: Optional[Path] = None) -> List[str]:
        """List available POMs."""
        poms_dir = poms_dir or cls.DEFAULT_POMS_DIR
        if not poms_dir.exists():
            return []
        return [d.name for d in poms_dir.iterdir()
                if d.is_dir() and (d / 'elements.json').exists()]


# Convenience function for iPython usage
def load_pom(app_name: str, driver: WebDriver = None, poms_dir: str = None) -> Union[BasePOM, POMData]:
    """
    Convenience function to load a POM.

    If driver is provided, returns a full BasePOM.
    If no driver, returns just the POMData for inspection.

    Example in iPython:
        from selectron.pom_loader import load_pom

        # Just inspect the data
        data = load_pom('Claude')
        print(data.elements.keys())

        # With driver for full functionality
        pom = load_pom('Claude', driver)
        pom.create_new_chat()
    """
    poms_path = Path(poms_dir) if poms_dir else None

    if driver:
        return POMLoader.load(app_name, driver, poms_path)
    else:
        return POMLoader.load_data(app_name, poms_path)
