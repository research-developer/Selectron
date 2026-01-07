#!/usr/bin/env python3
"""
Choice Engine - MidJourney-style answer selection system.

Generates multiple AI-powered answer choices that users can:
- Navigate with gamepad
- Upvote/downvote
- Re-roll (regenerate all)
- Create variants of specific answers
- Multi-select from inline lists

Integrates with the notification system for display.
"""

import sys
import time
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import (
    Any, Callable, Dict, List, Optional, Tuple, Union,
    AsyncGenerator, Protocol, TypeVar
)
from datetime import datetime
from threading import Lock
import uuid
import json

from .emulator import GamepadEmulator, GamepadButton, DPadDirection
from .menu import ANSI


class ChoiceStatus(Enum):
    """Status of a choice."""
    PENDING = auto()      # Not yet voted on
    UPVOTED = auto()      # User liked this
    DOWNVOTED = auto()    # User disliked this
    SELECTED = auto()     # User selected this as final answer
    VARIANT_SOURCE = auto()  # Used to generate variants


@dataclass
class AnswerChoice:
    """A single answer choice with metadata."""
    id: str
    content: str
    index: int  # Position in the choice set (0-3 typically)
    status: ChoiceStatus = ChoiceStatus.PENDING
    score: int = 0  # Upvotes minus downvotes
    metadata: Dict[str, Any] = field(default_factory=dict)
    parent_id: Optional[str] = None  # If this is a variant
    variant_number: int = 0  # V1, V2, V3, V4
    created_at: datetime = field(default_factory=datetime.now)

    def upvote(self) -> None:
        """Upvote this choice."""
        self.score += 1
        self.status = ChoiceStatus.UPVOTED

    def downvote(self) -> None:
        """Downvote this choice."""
        self.score -= 1
        self.status = ChoiceStatus.DOWNVOTED

    @property
    def label(self) -> str:
        """Get display label (1-4 or V1-V4)."""
        if self.parent_id:
            return f"V{self.variant_number}"
        return str(self.index + 1)


@dataclass
class ChoiceSet:
    """A set of choices for a question/prompt."""
    id: str
    prompt: str
    choices: List[AnswerChoice] = field(default_factory=list)
    context: str = ""  # Additional context
    source: str = ""   # Where this came from (iTerm, Slack, etc.)
    created_at: datetime = field(default_factory=datetime.now)
    generation: int = 1  # How many times re-rolled
    selected_indices: List[int] = field(default_factory=list)  # For multi-select
    is_multiselect: bool = False
    min_selections: int = 1
    max_selections: int = 1

    @property
    def selected_choices(self) -> List[AnswerChoice]:
        """Get currently selected choices."""
        return [c for c in self.choices if c.status == ChoiceStatus.SELECTED]

    def get_choice(self, index: int) -> Optional[AnswerChoice]:
        """Get choice by index."""
        if 0 <= index < len(self.choices):
            return self.choices[index]
        return None


class AnswerGenerator(ABC):
    """
    Abstract base class for AI answer generators.

    Implementations can use different AI backends:
    - OpenAI/Claude API
    - Local LLM
    - Rule-based generation
    - Mock for testing
    """

    @abstractmethod
    async def generate_choices(
        self,
        prompt: str,
        count: int = 4,
        context: Optional[str] = None,
    ) -> List[str]:
        """
        Generate multiple answer choices for a prompt.

        Args:
            prompt: The question/prompt to answer
            count: Number of choices to generate (default 4)
            context: Additional context for generation

        Returns:
            List of answer strings
        """
        pass

    @abstractmethod
    async def generate_variants(
        self,
        original: str,
        prompt: str,
        count: int = 4,
        context: Optional[str] = None,
    ) -> List[str]:
        """
        Generate variants of an existing answer.

        Args:
            original: The original answer to create variants of
            prompt: The original prompt
            count: Number of variants to generate
            context: Additional context

        Returns:
            List of variant answer strings
        """
        pass


class MockAnswerGenerator(AnswerGenerator):
    """Mock generator for testing without AI."""

    async def generate_choices(
        self,
        prompt: str,
        count: int = 4,
        context: Optional[str] = None,
    ) -> List[str]:
        """Generate mock choices."""
        await asyncio.sleep(0.5)  # Simulate API latency

        # Generate simple variations
        base_responses = [
            f"Option A: A thoughtful response to '{prompt[:30]}...'",
            f"Option B: An alternative approach considering the context",
            f"Option C: A creative solution that thinks outside the box",
            f"Option D: A practical, straightforward answer",
        ]
        return base_responses[:count]

    async def generate_variants(
        self,
        original: str,
        prompt: str,
        count: int = 4,
        context: Optional[str] = None,
    ) -> List[str]:
        """Generate mock variants."""
        await asyncio.sleep(0.3)

        return [
            f"{original} (variant {i+1} - slightly modified)"
            for i in range(count)
        ]


class ChoiceEngine:
    """
    Manages the generation, display, and selection of answer choices.

    Features:
    - Generate multiple AI-powered choices
    - Re-roll (regenerate) all choices
    - Create variants of specific choices
    - Track upvotes/downvotes
    - Support multi-select
    - History of choice sets

    Gamepad Controls:
    - D-pad Up/Down: Navigate choices
    - A: Select/confirm choice
    - B: Cancel/dismiss
    - X: Re-roll all (regenerate)
    - Y: Make variant of current selection
    - LB: Downvote current
    - RB: Upvote current
    - LT: Toggle selection (multi-select mode)
    - RT: Confirm multi-selection
    """

    def __init__(
        self,
        generator: Optional[AnswerGenerator] = None,
        gamepad: Optional[GamepadEmulator] = None,
    ):
        self.generator = generator or MockAnswerGenerator()
        self.gamepad = gamepad

        # Current state
        self._current_set: Optional[ChoiceSet] = None
        self._current_index: int = 0
        self._is_active: bool = False

        # History
        self._history: List[ChoiceSet] = []
        self._max_history = 50

        # Callbacks
        self._on_choice_selected: Optional[Callable[[AnswerChoice], None]] = None
        self._on_choices_updated: Optional[Callable[[ChoiceSet], None]] = None
        self._on_dismissed: Optional[Callable[[], None]] = None

        # Lock for thread safety
        self._lock = Lock()

        # Set up gamepad if provided
        if self.gamepad:
            self._setup_gamepad()

    def _setup_gamepad(self) -> None:
        """Set up gamepad controls."""
        def on_button(button: GamepadButton, pressed: bool):
            if not pressed or not self._is_active:
                return

            if button == GamepadButton.A:
                self._select_current()
            elif button == GamepadButton.B:
                self._dismiss()
            elif button == GamepadButton.X:
                asyncio.create_task(self._reroll())
            elif button == GamepadButton.Y:
                asyncio.create_task(self._make_variant())
            elif button == GamepadButton.LB:
                self._downvote_current()
            elif button == GamepadButton.RB:
                self._upvote_current()
            elif button == GamepadButton.LT:
                self._toggle_selection()
            elif button == GamepadButton.RT:
                self._confirm_multiselect()

        def on_dpad(direction: DPadDirection):
            if not self._is_active:
                return

            if direction == DPadDirection.UP:
                self._navigate(-1)
            elif direction == DPadDirection.DOWN:
                self._navigate(1)

        self.gamepad.on_button(on_button)
        self.gamepad.on_dpad(on_dpad)

    # === Callbacks ===

    def on_choice_selected(self, callback: Callable[[AnswerChoice], None]) -> None:
        """Set callback for when a choice is selected."""
        self._on_choice_selected = callback

    def on_choices_updated(self, callback: Callable[[ChoiceSet], None]) -> None:
        """Set callback for when choices are updated."""
        self._on_choices_updated = callback

    def on_dismissed(self, callback: Callable[[], None]) -> None:
        """Set callback for when choices are dismissed."""
        self._on_dismissed = callback

    # === Core Operations ===

    async def generate(
        self,
        prompt: str,
        context: str = "",
        source: str = "manual",
        count: int = 4,
        multiselect: bool = False,
        min_selections: int = 1,
        max_selections: int = 1,
    ) -> ChoiceSet:
        """
        Generate a new set of choices for a prompt.

        Args:
            prompt: The question/prompt
            context: Additional context
            source: Where this came from
            count: Number of choices to generate
            multiselect: Allow selecting multiple choices
            min_selections: Minimum required selections (multiselect)
            max_selections: Maximum allowed selections (multiselect)

        Returns:
            The generated ChoiceSet
        """
        # Generate answers
        answers = await self.generator.generate_choices(prompt, count, context)

        # Create choice set
        choice_set = ChoiceSet(
            id=str(uuid.uuid4()),
            prompt=prompt,
            context=context,
            source=source,
            is_multiselect=multiselect,
            min_selections=min_selections,
            max_selections=max_selections if multiselect else 1,
        )

        # Create choices
        for i, answer in enumerate(answers):
            choice = AnswerChoice(
                id=str(uuid.uuid4()),
                content=answer,
                index=i,
            )
            choice_set.choices.append(choice)

        # Set as current
        with self._lock:
            self._current_set = choice_set
            self._current_index = 0
            self._is_active = True

        # Add to history
        self._add_to_history(choice_set)

        # Callback
        if self._on_choices_updated:
            self._on_choices_updated(choice_set)

        return choice_set

    async def reroll(self) -> Optional[ChoiceSet]:
        """Re-roll (regenerate) all choices."""
        if not self._current_set:
            return None

        # Increment generation
        generation = self._current_set.generation + 1

        # Generate new choices
        new_set = await self.generate(
            prompt=self._current_set.prompt,
            context=self._current_set.context,
            source=self._current_set.source,
            count=len(self._current_set.choices),
            multiselect=self._current_set.is_multiselect,
            min_selections=self._current_set.min_selections,
            max_selections=self._current_set.max_selections,
        )

        new_set.generation = generation
        return new_set

    async def make_variant(self, choice_index: int) -> Optional[ChoiceSet]:
        """
        Create variants of a specific choice.

        Args:
            choice_index: Index of the choice to create variants of

        Returns:
            New ChoiceSet with variants
        """
        if not self._current_set:
            return None

        original_choice = self._current_set.get_choice(choice_index)
        if not original_choice:
            return None

        # Mark original as variant source
        original_choice.status = ChoiceStatus.VARIANT_SOURCE

        # Generate variants
        variants = await self.generator.generate_variants(
            original=original_choice.content,
            prompt=self._current_set.prompt,
            count=4,
            context=self._current_set.context,
        )

        # Create variant choice set
        variant_set = ChoiceSet(
            id=str(uuid.uuid4()),
            prompt=f"Variants of: {original_choice.content[:50]}...",
            context=self._current_set.context,
            source=self._current_set.source,
        )

        for i, variant in enumerate(variants):
            choice = AnswerChoice(
                id=str(uuid.uuid4()),
                content=variant,
                index=i,
                parent_id=original_choice.id,
                variant_number=i + 1,
            )
            variant_set.choices.append(choice)

        # Set as current
        with self._lock:
            self._current_set = variant_set
            self._current_index = 0

        # Add to history
        self._add_to_history(variant_set)

        # Callback
        if self._on_choices_updated:
            self._on_choices_updated(variant_set)

        return variant_set

    def select(self, choice_index: int) -> Optional[AnswerChoice]:
        """Select a choice as the final answer."""
        if not self._current_set:
            return None

        choice = self._current_set.get_choice(choice_index)
        if not choice:
            return None

        if self._current_set.is_multiselect:
            # Toggle selection in multiselect mode
            if choice.status == ChoiceStatus.SELECTED:
                choice.status = ChoiceStatus.PENDING
                if choice_index in self._current_set.selected_indices:
                    self._current_set.selected_indices.remove(choice_index)
            else:
                if len(self._current_set.selected_indices) < self._current_set.max_selections:
                    choice.status = ChoiceStatus.SELECTED
                    self._current_set.selected_indices.append(choice_index)
        else:
            # Single select - mark as selected and close
            choice.status = ChoiceStatus.SELECTED
            self._is_active = False

            if self._on_choice_selected:
                self._on_choice_selected(choice)

        return choice

    def upvote(self, choice_index: int) -> None:
        """Upvote a choice."""
        if not self._current_set:
            return

        choice = self._current_set.get_choice(choice_index)
        if choice:
            choice.upvote()
            if self._on_choices_updated:
                self._on_choices_updated(self._current_set)

    def downvote(self, choice_index: int) -> None:
        """Downvote a choice."""
        if not self._current_set:
            return

        choice = self._current_set.get_choice(choice_index)
        if choice:
            choice.downvote()
            if self._on_choices_updated:
                self._on_choices_updated(self._current_set)

    def dismiss(self) -> None:
        """Dismiss the current choice set without selecting."""
        with self._lock:
            self._is_active = False
            self._current_set = None

        if self._on_dismissed:
            self._on_dismissed()

    # === Navigation ===

    def _navigate(self, delta: int) -> None:
        """Navigate through choices."""
        if not self._current_set:
            return

        max_index = len(self._current_set.choices) - 1
        self._current_index = max(0, min(max_index, self._current_index + delta))

        if self._on_choices_updated:
            self._on_choices_updated(self._current_set)

    def _select_current(self) -> None:
        """Select the current choice."""
        self.select(self._current_index)

    def _upvote_current(self) -> None:
        """Upvote the current choice."""
        self.upvote(self._current_index)

    def _downvote_current(self) -> None:
        """Downvote the current choice."""
        self.downvote(self._current_index)

    async def _reroll(self) -> None:
        """Re-roll all choices."""
        await self.reroll()

    async def _make_variant(self) -> None:
        """Make variants of current choice."""
        await self.make_variant(self._current_index)

    def _toggle_selection(self) -> None:
        """Toggle selection in multiselect mode."""
        if self._current_set and self._current_set.is_multiselect:
            self.select(self._current_index)

    def _confirm_multiselect(self) -> None:
        """Confirm multiselect selections."""
        if not self._current_set or not self._current_set.is_multiselect:
            return

        if len(self._current_set.selected_indices) >= self._current_set.min_selections:
            self._is_active = False
            for choice in self._current_set.selected_choices:
                if self._on_choice_selected:
                    self._on_choice_selected(choice)

    def _dismiss(self) -> None:
        """Dismiss choices."""
        self.dismiss()

    # === History ===

    def _add_to_history(self, choice_set: ChoiceSet) -> None:
        """Add choice set to history."""
        self._history.append(choice_set)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def get_history(self, limit: int = 10) -> List[ChoiceSet]:
        """Get recent choice sets from history."""
        return self._history[-limit:]

    # === Properties ===

    @property
    def current_set(self) -> Optional[ChoiceSet]:
        """Get current choice set."""
        return self._current_set

    @property
    def current_index(self) -> int:
        """Get current navigation index."""
        return self._current_index

    @property
    def is_active(self) -> bool:
        """Check if choice engine is active."""
        return self._is_active


class ChoicePanel:
    """
    UI panel for displaying and interacting with choices.

    Renders choices with:
    - Current selection highlight
    - Vote indicators
    - Variant labels
    - Multi-select checkboxes
    - Action hints
    """

    def __init__(self, engine: ChoiceEngine):
        self.engine = engine

        # Register for updates
        engine.on_choices_updated(self._on_update)

    def _on_update(self, choice_set: ChoiceSet) -> None:
        """Handle choice set updates."""
        self.render()

    def render(self) -> List[str]:
        """Render the choice panel."""
        lines = []
        choice_set = self.engine.current_set

        if not choice_set:
            return ["No choices to display"]

        # Header
        lines.append(f"{ANSI.BOLD}{'─' * 60}{ANSI.RESET}")

        # Source and generation info
        source_info = f"[{choice_set.source}]" if choice_set.source else ""
        gen_info = f"Gen {choice_set.generation}" if choice_set.generation > 1 else ""
        lines.append(f"{ANSI.DIM}{source_info} {gen_info}{ANSI.RESET}")

        # Prompt
        lines.append(f"{ANSI.CYAN}{choice_set.prompt}{ANSI.RESET}")
        lines.append("")

        # Choices
        for i, choice in enumerate(choice_set.choices):
            is_current = i == self.engine.current_index
            lines.extend(self._render_choice(choice, is_current, choice_set.is_multiselect))

        # Footer with controls
        lines.append("")
        lines.append(f"{ANSI.DIM}{'─' * 60}{ANSI.RESET}")

        if choice_set.is_multiselect:
            selected = len(choice_set.selected_indices)
            lines.append(f"{ANSI.DIM}Selected: {selected}/{choice_set.max_selections} "
                        f"(min: {choice_set.min_selections}){ANSI.RESET}")
            lines.append(f"{ANSI.DIM}[A] Toggle  [RT] Confirm  [X] Re-roll  [Y] Variant  [B] Cancel{ANSI.RESET}")
        else:
            lines.append(f"{ANSI.DIM}[A] Select  [X] Re-roll  [Y] Variant  [LB] Down  [RB] Up  [B] Cancel{ANSI.RESET}")

        return lines

    def _render_choice(
        self,
        choice: AnswerChoice,
        is_current: bool,
        is_multiselect: bool,
    ) -> List[str]:
        """Render a single choice."""
        lines = []

        # Prefix
        if is_current:
            prefix = f"{ANSI.GREEN}▶{ANSI.RESET}"
            color = ANSI.GREEN
        else:
            prefix = " "
            color = ANSI.RESET

        # Checkbox for multiselect
        if is_multiselect:
            check = "☑" if choice.status == ChoiceStatus.SELECTED else "☐"
            prefix = f"{prefix} {check}"

        # Label (1-4 or V1-V4)
        label = choice.label

        # Vote indicator
        if choice.score > 0:
            vote = f"{ANSI.GREEN}+{choice.score}{ANSI.RESET}"
        elif choice.score < 0:
            vote = f"{ANSI.RED}{choice.score}{ANSI.RESET}"
        else:
            vote = ""

        # Status indicator
        status_icon = ""
        if choice.status == ChoiceStatus.UPVOTED:
            status_icon = " 👍"
        elif choice.status == ChoiceStatus.DOWNVOTED:
            status_icon = " 👎"
        elif choice.status == ChoiceStatus.SELECTED:
            status_icon = " ✓"
        elif choice.status == ChoiceStatus.VARIANT_SOURCE:
            status_icon = " 🔀"

        # Main line
        main_line = f"{prefix} [{label}]{status_icon} {vote}"
        lines.append(f"{color}{main_line}{ANSI.RESET}")

        # Content (wrapped)
        content = choice.content
        if len(content) > 55:
            content = content[:52] + "..."
        lines.append(f"     {ANSI.DIM if not is_current else ''}{content}{ANSI.RESET}")

        return lines

    def print_panel(self) -> None:
        """Print the panel to stdout."""
        lines = self.render()
        for line in lines:
            print(line)


# === Inline Multi-Select List ===

@dataclass
class InlineListItem:
    """An item in an inline multi-select list."""
    id: str
    label: str
    value: Any
    selected: bool = False
    group: Optional[str] = None


class InlineListSelector:
    """
    Inline multi-select list for selecting multiple values.

    Displays items inline (horizontally) with gamepad navigation.
    Useful for selecting tags, categories, options, etc.
    """

    def __init__(
        self,
        items: List[InlineListItem],
        gamepad: Optional[GamepadEmulator] = None,
        min_selections: int = 0,
        max_selections: int = 0,  # 0 = unlimited
    ):
        self.items = items
        self.gamepad = gamepad
        self.min_selections = min_selections
        self.max_selections = max_selections

        self._current_index = 0
        self._is_active = False

        # Callbacks
        self._on_selection_changed: Optional[Callable[[List[InlineListItem]], None]] = None
        self._on_confirmed: Optional[Callable[[List[Any]], None]] = None

        if gamepad:
            self._setup_gamepad()

    def _setup_gamepad(self) -> None:
        """Set up gamepad controls for inline navigation."""
        def on_button(button: GamepadButton, pressed: bool):
            if not pressed or not self._is_active:
                return

            if button == GamepadButton.A:
                self._toggle_current()
            elif button == GamepadButton.B:
                self._is_active = False
            elif button == GamepadButton.START:
                self._confirm()

        def on_dpad(direction: DPadDirection):
            if not self._is_active:
                return

            if direction == DPadDirection.LEFT:
                self._navigate(-1)
            elif direction == DPadDirection.RIGHT:
                self._navigate(1)

        self.gamepad.on_button(on_button)
        self.gamepad.on_dpad(on_dpad)

    def _navigate(self, delta: int) -> None:
        """Navigate left/right through items."""
        max_index = len(self.items) - 1
        self._current_index = max(0, min(max_index, self._current_index + delta))

    def _toggle_current(self) -> None:
        """Toggle selection of current item."""
        if not self.items:
            return

        item = self.items[self._current_index]
        selected_count = sum(1 for i in self.items if i.selected)

        if item.selected:
            item.selected = False
        elif self.max_selections == 0 or selected_count < self.max_selections:
            item.selected = True

        if self._on_selection_changed:
            self._on_selection_changed(self.selected_items)

    def _confirm(self) -> None:
        """Confirm selections."""
        if len(self.selected_items) >= self.min_selections:
            self._is_active = False
            if self._on_confirmed:
                self._on_confirmed([i.value for i in self.selected_items])

    @property
    def selected_items(self) -> List[InlineListItem]:
        """Get selected items."""
        return [i for i in self.items if i.selected]

    def on_selection_changed(self, callback: Callable[[List[InlineListItem]], None]) -> None:
        """Set callback for selection changes."""
        self._on_selection_changed = callback

    def on_confirmed(self, callback: Callable[[List[Any]], None]) -> None:
        """Set callback for confirmation."""
        self._on_confirmed = callback

    def activate(self) -> None:
        """Activate the selector."""
        self._is_active = True
        self._current_index = 0

    def render(self) -> str:
        """Render inline list as a single line."""
        parts = []

        for i, item in enumerate(self.items):
            is_current = i == self._current_index and self._is_active

            # Build item display
            if item.selected:
                check = "●"
                color = ANSI.GREEN
            else:
                check = "○"
                color = ANSI.DIM

            if is_current:
                display = f"{ANSI.UNDERLINE}[{check} {item.label}]{ANSI.RESET}"
            else:
                display = f"{color}[{check} {item.label}]{ANSI.RESET}"

            parts.append(display)

        return "  ".join(parts)


def create_choice_engine(
    generator: Optional[AnswerGenerator] = None,
    gamepad: Optional[GamepadEmulator] = None,
) -> ChoiceEngine:
    """Create a configured ChoiceEngine."""
    return ChoiceEngine(generator=generator, gamepad=gamepad)
