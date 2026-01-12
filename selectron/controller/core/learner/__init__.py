"""
Learning subsystem for gamepad button mapping.

This module provides an AI-powered learning system that:
1. Detects unmapped button presses
2. Records screen activity around the cursor
3. Analyzes recordings with Gemini vision
4. Learns and stores actions for replay

Usage:
    from selectron.controller.core.learner import LearningController
    from selectron.controller.core.mapper import ControllerMapper
    from selectron.controller.core.emulator import GamepadEmulator

    gamepad = GamepadEmulator()
    mapper = ControllerMapper(gamepad)
    learner = LearningController(mapper)

    # Now unmapped button presses trigger learning
"""

import asyncio
import time
import threading
from pathlib import Path
from typing import Dict, Optional, Callable, Any

from ..emulator import GamepadButton
from ..mapper import ControllerMapper
from .feedback import LearningFeedback, FeedbackType
from .store import ActionStore, LearnedAction
from .agent import ButtonLearningAgent, MockLearningAgent


# Default sound file location
DEFAULT_SOUND_PATH = Path(__file__).parents[4] / "assets" / "notification.wav"


class LearningController:
    """
    Orchestrates the learning system for gamepad button mapping.

    Listens for unmapped button presses, enters learning mode to record
    user demonstrations, analyzes recordings with AI, and stores learned
    actions for replay.

    Timing thresholds:
    - 2 second hold: Start learning for unmapped button
    - 5 second hold: Force re-learn for mapped button
    - 3 consecutive failures: Auto-trigger re-learn
    """

    # Timing thresholds (seconds)
    NEW_LEARN_HOLD = 2.0      # Hold duration to start learning (unmapped)
    RELEARN_HOLD = 5.0        # Hold duration to force re-learn (mapped)
    RECORD_TIMEOUT = 5.0      # Max recording duration

    # Failure threshold for auto-relearn
    MAX_FAILURES = 3

    def __init__(
        self,
        mapper: ControllerMapper,
        store: Optional[ActionStore] = None,
        agent: Optional[ButtonLearningAgent] = None,
        sound_path: Optional[Path] = None,
        action_executor: Optional[Callable[[LearnedAction], bool]] = None,
        use_mock_agent: bool = False,
    ):
        """
        Initialize the learning controller.

        Args:
            mapper: ControllerMapper to hook into for unmapped events.
            store: ActionStore for persistence (creates default if None).
            agent: Learning agent (creates default if None).
            sound_path: Path to notification sound.
            action_executor: Function to execute learned actions.
                            Returns True if action succeeded.
            use_mock_agent: Use MockLearningAgent for testing.
        """
        self.mapper = mapper
        self.store = store if store is not None else ActionStore()

        if use_mock_agent:
            self.agent = MockLearningAgent()
        else:
            self.agent = agent if agent is not None else ButtonLearningAgent()

        # Find sound file
        if sound_path is None:
            sound_path = DEFAULT_SOUND_PATH if DEFAULT_SOUND_PATH.exists() else None

        self.feedback = LearningFeedback(sound_path=sound_path)
        self.action_executor = action_executor or self._default_executor

        # State tracking
        self._button_press_times: Dict[GamepadButton, float] = {}
        self._recording_button: Optional[GamepadButton] = None
        self._stop_recording = False
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None

        # Register for unmapped buttons
        mapper.on_unmapped(self._handle_unmapped)

    def _get_event_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create an event loop for async operations."""
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            if self._event_loop is None or self._event_loop.is_closed():
                self._event_loop = asyncio.new_event_loop()
            return self._event_loop

    def _run_async(self, coro) -> None:
        """Run a coroutine, handling event loop creation."""
        try:
            loop = asyncio.get_running_loop()
            # Already in async context - create task
            asyncio.create_task(coro)
        except RuntimeError:
            # No running loop - run in thread
            def run_in_thread():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(coro)
                finally:
                    loop.close()

            thread = threading.Thread(target=run_in_thread, daemon=True)
            thread.start()

    def _handle_unmapped(self, button: GamepadButton, pressed: bool) -> None:
        """
        Handle unmapped button press/release events.

        This is called by the ControllerMapper when a button without
        a binding is pressed or released.
        """
        now = time.time()

        if pressed:
            # Record press time
            self._button_press_times[button] = now

            # If we're already recording and this button is pressed, stop recording
            if self._recording_button == button:
                self._stop_recording = True

        else:  # Released
            press_time = self._button_press_times.get(button, now)
            hold_duration = now - press_time

            # Check if this button has a learned action
            existing_action = self.store.get(button)

            if existing_action:
                # Button has a learned action
                if hold_duration >= self.RELEARN_HOLD:
                    # Long hold - force re-learn
                    self.feedback.flash(FeedbackType.RELEARN)
                    self._run_async(self._start_learning(button, force=True))

                elif self.store.should_relearn(button, self.MAX_FAILURES):
                    # Too many failures - auto re-learn
                    self.feedback.flash(FeedbackType.RELEARN)
                    self._run_async(self._start_learning(button, force=True))

                else:
                    # Execute the learned action
                    self._run_async(self._execute_learned(button, existing_action))

            else:
                # No learned action
                if hold_duration >= self.NEW_LEARN_HOLD:
                    # Hold threshold met - start learning
                    self._run_async(self._start_learning(button))
                else:
                    # Quick press - just notify
                    print(f"[LearningController] Button {button.name} unmapped. "
                          f"Hold {self.NEW_LEARN_HOLD}s to learn.")

    async def _start_learning(self, button: GamepadButton, force: bool = False) -> None:
        """
        Enter learning mode and record user demonstration.

        Args:
            button: The button to learn.
            force: If True, overwrite existing action.
        """
        from ...bridges.macos.screen import capture_around_cursor

        self._recording_button = button
        self._stop_recording = False

        print(f"[LearningController] Starting learning for {button.name}...")
        self.feedback.start_learning()

        # Capture frames until button press or timeout
        frames = []
        start = time.time()
        frame_interval = 0.1  # 10 FPS

        while not self._stop_recording and (time.time() - start) < self.RECORD_TIMEOUT:
            try:
                frame = capture_around_cursor(radius=200)
                frames.append(frame)
            except Exception as e:
                print(f"[LearningController] Capture error: {e}")

            await asyncio.sleep(frame_interval)

        self._recording_button = None

        # Stop learning feedback
        self.feedback.stop_learning(success=True)

        print(f"[LearningController] Recorded {len(frames)} frames. Analyzing...")

        # Analyze with agent
        try:
            action = await self.agent.analyze_recording(frames, button)

            # Save the action
            self.store.save(action)

            print(f"[LearningController] Learned: {action.description}")
            print(f"  Action: {action.action_type}")
            print(f"  Confidence: {action.confidence:.0%}")

            self.feedback.flash(FeedbackType.SUCCESS)

        except Exception as e:
            print(f"[LearningController] Analysis failed: {e}")
            self.feedback.flash(FeedbackType.FAILED)

    async def _execute_learned(self, button: GamepadButton, action: LearnedAction) -> None:
        """
        Execute a previously learned action.

        Args:
            button: The button that was pressed.
            action: The learned action to execute.
        """
        print(f"[LearningController] Executing: {action.description}")
        self.feedback.flash(FeedbackType.ATTEMPTING)

        try:
            success = await self._run_action_executor(action)
            self.store.record_result(button, success)

            if success:
                print(f"[LearningController] Action succeeded")
                self.feedback.flash(FeedbackType.SUCCESS)
            else:
                print(f"[LearningController] Action failed")
                self.feedback.flash(FeedbackType.FAILED)

        except Exception as e:
            print(f"[LearningController] Execution error: {e}")
            self.store.record_result(button, False)
            self.feedback.flash(FeedbackType.FAILED)

    async def _run_action_executor(self, action: LearnedAction) -> bool:
        """Run the action executor (sync or async)."""
        result = self.action_executor(action)
        if asyncio.iscoroutine(result):
            return await result
        return result

    def _default_executor(self, action: LearnedAction) -> bool:
        """
        Default action executor - logs action but doesn't perform it.

        Override with action_executor parameter to actually execute actions.
        """
        print(f"[LearningController] Would execute: {action.action_type}")
        print(f"  Parameters: {action.parameters}")

        # Simulate success for testing
        return True

    # === Manual Learning Control ===

    def learn_button(self, button: GamepadButton) -> None:
        """
        Manually trigger learning for a button.

        Args:
            button: Button to learn.
        """
        self._run_async(self._start_learning(button, force=True))

    def forget_button(self, button: GamepadButton) -> bool:
        """
        Delete the learned action for a button.

        Args:
            button: Button to forget.

        Returns:
            True if an action was deleted.
        """
        return self.store.delete(button)

    def get_action(self, button: GamepadButton) -> Optional[LearnedAction]:
        """
        Get the learned action for a button.

        Args:
            button: Button to query.

        Returns:
            LearnedAction if one exists.
        """
        return self.store.get(button)

    def list_learned(self) -> list:
        """Get all learned actions."""
        return self.store.list_all()


# Export key classes
__all__ = [
    'LearningController',
    'LearningFeedback',
    'FeedbackType',
    'ActionStore',
    'LearnedAction',
    'ButtonLearningAgent',
    'MockLearningAgent',
]
