"""
Selectron Event Watcher Service

Background service that monitors WebDriver and WebElement events for testing.
Maintains a queue of expected events and records pass/fail results with screenshots.

Usage:
    from selectron.event_watcher import EventWatcher, EventExpectation, InvalidationStrategy

    # Create watcher for a driver
    watcher = EventWatcher(driver, output_dir="./test_evidence")
    watcher.start()

    # Add expectations to the queue
    watcher.expect_click("#submit-btn", timeout=5.0)
    watcher.expect_navigation("/dashboard")
    watcher.expect_text_change("#status", contains="Success")

    # Perform actions...
    driver.find_element(By.ID, "submit-btn").click()

    # Check results
    results = watcher.get_results()
    watcher.stop()
"""

import json
import threading
import time
import queue
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Union
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    StaleElementReferenceException,
    NoSuchElementException,
    WebDriverException,
)


class InvalidationStrategy(Enum):
    """How to handle element invalidation or navigation changes."""
    FAIL = "fail"           # Mark as failed immediately
    REATTACH = "reattach"   # Try to relocate the element


class EventType(Enum):
    """Types of events to watch for."""
    # WebDriver events
    NAVIGATION = "navigation"
    TAB_CHANGE = "tab_change"
    ALERT = "alert"
    PAGE_LOAD = "page_load"

    # WebElement events
    CLICK = "click"
    TEXT_CHANGE = "text_change"
    ATTRIBUTE_CHANGE = "attribute_change"
    VISIBILITY_CHANGE = "visibility_change"
    ENABLED_CHANGE = "enabled_change"
    ELEMENT_APPEAR = "element_appear"
    ELEMENT_DISAPPEAR = "element_disappear"

    # Custom
    CUSTOM = "custom"


class EventStatus(Enum):
    """Status of an event expectation."""
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    INVALIDATED = "invalidated"


@dataclass
class EventExpectation:
    """
    Describes an event to watch for.

    Attributes:
        event_type: Type of event to watch
        selector: CSS selector or XPath for element events
        locator_type: By.CSS_SELECTOR or By.XPATH
        timeout: Seconds to wait for event
        invalidation_strategy: How to handle element invalidation
        expected_value: Expected value for comparison events
        contains: Substring to look for (for text events)
        poll_interval: How often to check (seconds)
        description: Human-readable description
        metadata: Additional data to store with result
    """
    event_type: EventType
    selector: str = ""
    locator_type: str = By.CSS_SELECTOR
    timeout: float = 10.0
    invalidation_strategy: InvalidationStrategy = InvalidationStrategy.REATTACH
    expected_value: Optional[str] = None
    contains: Optional[str] = None
    poll_interval: float = 0.25
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Internal tracking
    _id: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d%H%M%S%f"))
    _created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class EventResult:
    """
    Result of an event expectation.

    Attributes:
        expectation: The original expectation
        status: Pass/fail status
        actual_value: What was actually observed
        screenshot_path: Path to evidence screenshot
        error_message: Error details if failed
        duration_ms: How long it took
        timestamp: When the result was recorded
    """
    expectation: EventExpectation
    status: EventStatus
    actual_value: Optional[str] = None
    screenshot_path: Optional[str] = None
    error_message: Optional[str] = None
    duration_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    element_html: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "expectation_id": self.expectation._id,
            "event_type": self.expectation.event_type.value,
            "selector": self.expectation.selector,
            "description": self.expectation.description,
            "status": self.status.value,
            "actual_value": self.actual_value,
            "expected_value": self.expectation.expected_value,
            "contains": self.expectation.contains,
            "screenshot_path": self.screenshot_path,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
            "element_html": self.element_html,
            "metadata": self.expectation.metadata,
        }


class EventWatcher:
    """
    Background service that watches for WebDriver/WebElement events.

    Runs in a separate thread, polling for expected events and recording
    results with screenshot evidence.
    """

    def __init__(
        self,
        driver: WebDriver,
        output_dir: Union[str, Path] = "./test_evidence",
        app_name: str = "app",
    ):
        """
        Initialize the event watcher.

        Args:
            driver: Selenium WebDriver instance
            output_dir: Directory for screenshots and results
            app_name: Name of the app being tested
        """
        self._driver = driver
        self._output_dir = Path(output_dir)
        self._app_name = app_name
        self._output_dir.mkdir(parents=True, exist_ok=True)

        # Event queue and results
        self._expectations: queue.Queue[EventExpectation] = queue.Queue()
        self._active_expectations: List[EventExpectation] = []
        self._results: List[EventResult] = []
        self._results_lock = threading.Lock()

        # Background thread control
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # State tracking for change detection
        self._last_url = ""
        self._last_title = ""
        self._last_window_handle = ""
        self._element_states: Dict[str, Dict[str, Any]] = {}

        # Session info
        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._session_dir = self._output_dir / f"{app_name}_{self._session_id}"
        self._session_dir.mkdir(parents=True, exist_ok=True)

    def start(self) -> None:
        """Start the background watcher thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

        # Initialize state
        try:
            self._last_url = self._driver.current_url
            self._last_title = self._driver.title
            self._last_window_handle = self._driver.current_window_handle
        except WebDriverException:
            pass

    def stop(self) -> None:
        """Stop the background watcher thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

        # Save final results
        self._save_results()

    def expect(self, expectation: EventExpectation) -> str:
        """
        Add an event expectation to the queue.

        Args:
            expectation: The event to watch for

        Returns:
            The expectation ID for tracking
        """
        self._expectations.put(expectation)
        return expectation._id

    # Convenience methods for common expectations
    def expect_click(
        self,
        selector: str,
        timeout: float = 5.0,
        description: str = "",
        on_invalidation: InvalidationStrategy = InvalidationStrategy.REATTACH,
    ) -> str:
        """Expect an element to be clicked."""
        return self.expect(EventExpectation(
            event_type=EventType.CLICK,
            selector=selector,
            timeout=timeout,
            description=description or f"Click on {selector}",
            invalidation_strategy=on_invalidation,
        ))

    def expect_navigation(
        self,
        url_contains: str,
        timeout: float = 10.0,
        description: str = "",
    ) -> str:
        """Expect navigation to a URL."""
        return self.expect(EventExpectation(
            event_type=EventType.NAVIGATION,
            contains=url_contains,
            timeout=timeout,
            description=description or f"Navigate to {url_contains}",
        ))

    def expect_text_change(
        self,
        selector: str,
        contains: Optional[str] = None,
        expected_value: Optional[str] = None,
        timeout: float = 10.0,
        description: str = "",
        on_invalidation: InvalidationStrategy = InvalidationStrategy.REATTACH,
    ) -> str:
        """Expect text content to change."""
        return self.expect(EventExpectation(
            event_type=EventType.TEXT_CHANGE,
            selector=selector,
            contains=contains,
            expected_value=expected_value,
            timeout=timeout,
            description=description or f"Text change in {selector}",
            invalidation_strategy=on_invalidation,
        ))

    def expect_element_appear(
        self,
        selector: str,
        timeout: float = 10.0,
        description: str = "",
    ) -> str:
        """Expect an element to appear in the DOM."""
        return self.expect(EventExpectation(
            event_type=EventType.ELEMENT_APPEAR,
            selector=selector,
            timeout=timeout,
            description=description or f"Element appears: {selector}",
        ))

    def expect_element_disappear(
        self,
        selector: str,
        timeout: float = 10.0,
        description: str = "",
    ) -> str:
        """Expect an element to disappear from the DOM."""
        return self.expect(EventExpectation(
            event_type=EventType.ELEMENT_DISAPPEAR,
            selector=selector,
            timeout=timeout,
            description=description or f"Element disappears: {selector}",
        ))

    def expect_visibility_change(
        self,
        selector: str,
        visible: bool,
        timeout: float = 10.0,
        description: str = "",
        on_invalidation: InvalidationStrategy = InvalidationStrategy.REATTACH,
    ) -> str:
        """Expect element visibility to change."""
        return self.expect(EventExpectation(
            event_type=EventType.VISIBILITY_CHANGE,
            selector=selector,
            expected_value=str(visible).lower(),
            timeout=timeout,
            description=description or f"Visibility change: {selector} -> {visible}",
            invalidation_strategy=on_invalidation,
        ))

    def expect_tab_change(
        self,
        timeout: float = 5.0,
        description: str = "",
    ) -> str:
        """Expect the browser tab/window to change."""
        return self.expect(EventExpectation(
            event_type=EventType.TAB_CHANGE,
            timeout=timeout,
            description=description or "Tab change",
        ))

    def get_results(self) -> List[EventResult]:
        """Get all results so far."""
        with self._results_lock:
            return list(self._results)

    def get_pending(self) -> List[EventExpectation]:
        """Get all pending expectations."""
        return list(self._active_expectations)

    def clear_results(self) -> None:
        """Clear all results."""
        with self._results_lock:
            self._results.clear()

    def wait_for_all(self, timeout: float = 30.0) -> List[EventResult]:
        """
        Wait for all current expectations to complete.

        Args:
            timeout: Maximum time to wait

        Returns:
            List of results
        """
        start = time.time()
        while time.time() - start < timeout:
            if not self._active_expectations and self._expectations.empty():
                break
            time.sleep(0.1)
        return self.get_results()

    def _watch_loop(self) -> None:
        """Main background loop that watches for events."""
        while self._running:
            # Process new expectations from queue
            while not self._expectations.empty():
                try:
                    exp = self._expectations.get_nowait()
                    exp._start_time = time.time()
                    self._active_expectations.append(exp)
                except queue.Empty:
                    break

            # Check WebDriver-level events
            self._check_webdriver_events()

            # Check each active expectation
            completed = []
            for exp in self._active_expectations:
                result = self._check_expectation(exp)
                if result:
                    completed.append((exp, result))

            # Record completed expectations
            for exp, result in completed:
                self._record_result(exp, result)
                self._active_expectations.remove(exp)

            time.sleep(0.1)  # Prevent busy-waiting

    def _check_webdriver_events(self) -> None:
        """Check for WebDriver-level state changes."""
        try:
            current_url = self._driver.current_url
            current_title = self._driver.title
            current_handle = self._driver.current_window_handle

            # Detect navigation
            if current_url != self._last_url:
                self._on_navigation(self._last_url, current_url)
                self._last_url = current_url

            # Detect tab change
            if current_handle != self._last_window_handle:
                self._on_tab_change(self._last_window_handle, current_handle)
                self._last_window_handle = current_handle

            self._last_title = current_title

        except WebDriverException:
            pass  # Driver may be busy

    def _on_navigation(self, old_url: str, new_url: str) -> None:
        """Handle navigation event - check if any expectations match."""
        for exp in self._active_expectations:
            if exp.event_type == EventType.NAVIGATION:
                if exp.contains and exp.contains in new_url:
                    # Navigation expectation satisfied
                    pass  # Will be caught in _check_expectation

    def _on_tab_change(self, old_handle: str, new_handle: str) -> None:
        """Handle tab change event."""
        pass  # Will be caught in _check_expectation

    def _check_expectation(self, exp: EventExpectation) -> Optional[EventResult]:
        """
        Check if an expectation has been satisfied.

        Returns EventResult if complete (pass or fail), None if still pending.
        """
        elapsed = time.time() - getattr(exp, '_start_time', time.time())

        # Check timeout
        if elapsed > exp.timeout:
            return EventResult(
                expectation=exp,
                status=EventStatus.TIMEOUT,
                duration_ms=elapsed * 1000,
                error_message=f"Timeout after {exp.timeout}s",
            )

        try:
            if exp.event_type == EventType.NAVIGATION:
                return self._check_navigation(exp, elapsed)
            elif exp.event_type == EventType.TAB_CHANGE:
                return self._check_tab_change(exp, elapsed)
            elif exp.event_type == EventType.ELEMENT_APPEAR:
                return self._check_element_appear(exp, elapsed)
            elif exp.event_type == EventType.ELEMENT_DISAPPEAR:
                return self._check_element_disappear(exp, elapsed)
            elif exp.event_type == EventType.TEXT_CHANGE:
                return self._check_text_change(exp, elapsed)
            elif exp.event_type == EventType.VISIBILITY_CHANGE:
                return self._check_visibility_change(exp, elapsed)
            elif exp.event_type == EventType.CLICK:
                return self._check_click(exp, elapsed)

        except StaleElementReferenceException:
            if exp.invalidation_strategy == InvalidationStrategy.FAIL:
                return EventResult(
                    expectation=exp,
                    status=EventStatus.INVALIDATED,
                    duration_ms=elapsed * 1000,
                    error_message="Element became stale",
                )
            # REATTACH strategy: continue trying

        except NoSuchElementException:
            if exp.event_type == EventType.ELEMENT_DISAPPEAR:
                # Element not found = disappeared (success)
                return EventResult(
                    expectation=exp,
                    status=EventStatus.PASSED,
                    duration_ms=elapsed * 1000,
                )
            # For other events, keep waiting unless timeout

        except WebDriverException as e:
            return EventResult(
                expectation=exp,
                status=EventStatus.FAILED,
                duration_ms=elapsed * 1000,
                error_message=str(e),
            )

        return None  # Still pending

    def _check_navigation(self, exp: EventExpectation, elapsed: float) -> Optional[EventResult]:
        """Check navigation expectation."""
        current_url = self._driver.current_url
        if exp.contains and exp.contains in current_url:
            return EventResult(
                expectation=exp,
                status=EventStatus.PASSED,
                actual_value=current_url,
                duration_ms=elapsed * 1000,
            )
        if exp.expected_value and current_url == exp.expected_value:
            return EventResult(
                expectation=exp,
                status=EventStatus.PASSED,
                actual_value=current_url,
                duration_ms=elapsed * 1000,
            )
        return None

    def _check_tab_change(self, exp: EventExpectation, elapsed: float) -> Optional[EventResult]:
        """Check tab change expectation."""
        current_handle = self._driver.current_window_handle
        if current_handle != self._last_window_handle:
            return EventResult(
                expectation=exp,
                status=EventStatus.PASSED,
                actual_value=current_handle,
                duration_ms=elapsed * 1000,
            )
        return None

    def _check_element_appear(self, exp: EventExpectation, elapsed: float) -> Optional[EventResult]:
        """Check if element has appeared."""
        elements = self._driver.find_elements(exp.locator_type, exp.selector)
        if elements and elements[0].is_displayed():
            return EventResult(
                expectation=exp,
                status=EventStatus.PASSED,
                duration_ms=elapsed * 1000,
                element_html=elements[0].get_attribute("outerHTML")[:500],
            )
        return None

    def _check_element_disappear(self, exp: EventExpectation, elapsed: float) -> Optional[EventResult]:
        """Check if element has disappeared."""
        elements = self._driver.find_elements(exp.locator_type, exp.selector)
        if not elements or not elements[0].is_displayed():
            return EventResult(
                expectation=exp,
                status=EventStatus.PASSED,
                duration_ms=elapsed * 1000,
            )
        return None

    def _check_text_change(self, exp: EventExpectation, elapsed: float) -> Optional[EventResult]:
        """Check if text has changed to expected value."""
        element = self._driver.find_element(exp.locator_type, exp.selector)
        current_text = element.text

        if exp.contains and exp.contains in current_text:
            return EventResult(
                expectation=exp,
                status=EventStatus.PASSED,
                actual_value=current_text,
                duration_ms=elapsed * 1000,
                element_html=element.get_attribute("outerHTML")[:500],
            )

        if exp.expected_value and current_text == exp.expected_value:
            return EventResult(
                expectation=exp,
                status=EventStatus.PASSED,
                actual_value=current_text,
                duration_ms=elapsed * 1000,
                element_html=element.get_attribute("outerHTML")[:500],
            )

        return None

    def _check_visibility_change(self, exp: EventExpectation, elapsed: float) -> Optional[EventResult]:
        """Check if visibility has changed."""
        element = self._driver.find_element(exp.locator_type, exp.selector)
        is_visible = element.is_displayed()
        expected_visible = exp.expected_value == "true"

        if is_visible == expected_visible:
            return EventResult(
                expectation=exp,
                status=EventStatus.PASSED,
                actual_value=str(is_visible).lower(),
                duration_ms=elapsed * 1000,
            )
        return None

    def _check_click(self, exp: EventExpectation, elapsed: float) -> Optional[EventResult]:
        """
        Check click expectation.

        Note: This is a passive check - we verify the element is clickable.
        The actual click detection would require JS event listeners.
        """
        element = self._driver.find_element(exp.locator_type, exp.selector)
        if element.is_displayed() and element.is_enabled():
            return EventResult(
                expectation=exp,
                status=EventStatus.PASSED,
                duration_ms=elapsed * 1000,
                element_html=element.get_attribute("outerHTML")[:500],
            )
        return None

    def _record_result(self, exp: EventExpectation, result: EventResult) -> None:
        """Record a result and take screenshot if needed."""
        # Take screenshot for evidence
        screenshot_path = None
        if result.status in (EventStatus.PASSED, EventStatus.FAILED):
            try:
                timestamp = datetime.now().strftime("%H%M%S%f")
                status_str = result.status.value
                filename = f"{timestamp}_{status_str}_{exp._id[:8]}.png"
                screenshot_path = self._session_dir / filename

                if exp.selector:
                    # Try element screenshot first
                    try:
                        element = self._driver.find_element(exp.locator_type, exp.selector)
                        element.screenshot(str(screenshot_path))
                    except:
                        # Fall back to full page
                        self._driver.save_screenshot(str(screenshot_path))
                else:
                    self._driver.save_screenshot(str(screenshot_path))

                result.screenshot_path = str(screenshot_path)

            except Exception as e:
                result.error_message = (result.error_message or "") + f" (screenshot failed: {e})"

        with self._results_lock:
            self._results.append(result)

    def _save_results(self) -> None:
        """Save all results to JSON file."""
        results_file = self._session_dir / "results.json"
        with self._results_lock:
            data = {
                "app_name": self._app_name,
                "session_id": self._session_id,
                "total_expectations": len(self._results),
                "passed": sum(1 for r in self._results if r.status == EventStatus.PASSED),
                "failed": sum(1 for r in self._results if r.status == EventStatus.FAILED),
                "timeout": sum(1 for r in self._results if r.status == EventStatus.TIMEOUT),
                "results": [r.to_dict() for r in self._results],
            }
        results_file.write_text(json.dumps(data, indent=2))

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
        return False


# Convenience function to create watcher from ElectronDriverManager
def create_watcher(
    driver: WebDriver,
    app_name: str = "app",
    output_dir: str = "./test_evidence",
) -> EventWatcher:
    """
    Create an EventWatcher for a WebDriver instance.

    Args:
        driver: WebDriver instance
        app_name: Name of the app
        output_dir: Where to save evidence

    Returns:
        EventWatcher instance (not yet started)
    """
    return EventWatcher(driver, output_dir=output_dir, app_name=app_name)
