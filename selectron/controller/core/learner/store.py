"""
Persistent storage for learned button actions.

Stores learned actions in a JSON file with success/failure tracking
for confidence adjustment and auto-relearn triggering.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import threading

from ..emulator import GamepadButton


@dataclass
class LearnedAction:
    """
    A learned action associated with a gamepad button.

    Stores the action details and tracks success/failure
    for confidence scoring and re-learning decisions.
    """
    button: str  # GamepadButton.name
    action_type: str  # "click", "type", "key_combo", "scroll", "macro"
    parameters: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    confidence: float = 1.0

    # Timestamps
    created_at: str = ""
    last_used_at: str = ""
    last_modified_at: str = ""

    # Success tracking
    success_count: int = 0
    failure_count: int = 0

    # Raw data for debugging/retraining
    recorded_frames: int = 0  # How many frames were recorded
    analysis_summary: str = ""  # What the agent interpreted

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.last_modified_at:
            self.last_modified_at = self.created_at

    @property
    def total_uses(self) -> int:
        """Total number of times this action was executed."""
        return self.success_count + self.failure_count

    @property
    def success_rate(self) -> float:
        """Success rate as a percentage (0.0 to 1.0)."""
        if self.total_uses == 0:
            return 1.0
        return self.success_count / self.total_uses

    @property
    def consecutive_failures(self) -> int:
        """
        Estimate consecutive failures (simplified).

        Note: For accurate tracking, we'd need a history list.
        This uses a heuristic based on recent success rate.
        """
        # If success rate is very low and we have some uses, assume failures are recent
        if self.total_uses >= 3 and self.success_rate < 0.4:
            return min(3, self.failure_count)
        return 0

    def record_success(self) -> None:
        """Record a successful execution."""
        self.success_count += 1
        self.last_used_at = datetime.now().isoformat()
        # Boost confidence on success
        self.confidence = min(1.0, self.confidence + 0.1)

    def record_failure(self) -> None:
        """Record a failed execution."""
        self.failure_count += 1
        self.last_used_at = datetime.now().isoformat()
        # Reduce confidence on failure
        self.confidence = max(0.0, self.confidence - 0.2)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LearnedAction':
        """Create from dictionary (JSON deserialization)."""
        return cls(**data)


class ActionStore:
    """
    Persistent storage for learned button→action mappings.

    Stores actions in a JSON file at ~/.selectron/learned_actions.json
    with automatic loading and thread-safe saving.
    """

    DEFAULT_PATH = Path.home() / ".selectron" / "learned_actions.json"

    def __init__(self, path: Optional[Path] = None):
        """
        Initialize the action store.

        Args:
            path: Path to the JSON file. Uses default if not specified.
        """
        self.path = path or self.DEFAULT_PATH
        self._actions: Dict[str, LearnedAction] = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        """Load actions from disk."""
        if not self.path.exists():
            return

        try:
            with open(self.path, 'r') as f:
                data = json.load(f)

            for button_name, action_data in data.items():
                self._actions[button_name] = LearnedAction.from_dict(action_data)

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"Warning: Could not load learned actions: {e}")
            # Keep empty store, don't overwrite potentially corrupted file
            self._actions = {}

    def _persist(self) -> None:
        """Save actions to disk."""
        # Ensure directory exists
        self.path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            button_name: action.to_dict()
            for button_name, action in self._actions.items()
        }

        # Write atomically
        temp_path = self.path.with_suffix('.tmp')
        with open(temp_path, 'w') as f:
            json.dump(data, f, indent=2)
        temp_path.rename(self.path)

    def get(self, button: GamepadButton) -> Optional[LearnedAction]:
        """
        Get the learned action for a button.

        Args:
            button: The gamepad button.

        Returns:
            LearnedAction if one exists, None otherwise.
        """
        with self._lock:
            return self._actions.get(button.name)

    def save(self, action: LearnedAction) -> None:
        """
        Save a learned action.

        Args:
            action: The learned action to save.
        """
        with self._lock:
            action.last_modified_at = datetime.now().isoformat()
            self._actions[action.button] = action
            self._persist()

    def delete(self, button: GamepadButton) -> bool:
        """
        Delete a learned action.

        Args:
            button: The gamepad button.

        Returns:
            True if an action was deleted, False if none existed.
        """
        with self._lock:
            if button.name in self._actions:
                del self._actions[button.name]
                self._persist()
                return True
            return False

    def record_result(self, button: GamepadButton, success: bool) -> None:
        """
        Record the result of executing a learned action.

        Args:
            button: The gamepad button.
            success: Whether the action succeeded.
        """
        with self._lock:
            action = self._actions.get(button.name)
            if action:
                if success:
                    action.record_success()
                else:
                    action.record_failure()
                self._persist()

    def should_relearn(self, button: GamepadButton, max_failures: int = 3) -> bool:
        """
        Check if a button should be re-learned based on failure count.

        Args:
            button: The gamepad button.
            max_failures: Threshold for automatic re-learning.

        Returns:
            True if the button should be re-learned.
        """
        action = self.get(button)
        if not action:
            return False

        # Check consecutive failures or very low success rate
        return (
            action.consecutive_failures >= max_failures or
            (action.total_uses >= 5 and action.success_rate < 0.3)
        )

    def list_all(self) -> List[LearnedAction]:
        """Get all learned actions."""
        with self._lock:
            return list(self._actions.values())

    def clear(self) -> None:
        """Clear all learned actions."""
        with self._lock:
            self._actions.clear()
            self._persist()

    def __len__(self) -> int:
        """Number of learned actions."""
        return len(self._actions)

    def __contains__(self, button: GamepadButton) -> bool:
        """Check if a button has a learned action."""
        return button.name in self._actions


# === Demo ===

if __name__ == "__main__":
    from ..emulator import GamepadButton

    print("Action Store Test")
    print("=" * 40)

    # Use temp path for testing
    store = ActionStore(Path("/tmp/test_learned_actions.json"))

    # Create a test action
    action = LearnedAction(
        button=GamepadButton.A.name,
        action_type="click",
        parameters={"x": 100, "y": 200},
        description="Click at coordinates",
        recorded_frames=30,
        analysis_summary="User clicked on a button labeled 'Submit'",
    )

    # Save it
    store.save(action)
    print(f"Saved action for button A")

    # Retrieve it
    retrieved = store.get(GamepadButton.A)
    print(f"Retrieved: {retrieved}")

    # Record some results
    store.record_result(GamepadButton.A, success=True)
    store.record_result(GamepadButton.A, success=True)
    store.record_result(GamepadButton.A, success=False)

    retrieved = store.get(GamepadButton.A)
    print(f"After 2 success + 1 failure:")
    print(f"  Success rate: {retrieved.success_rate:.0%}")
    print(f"  Confidence: {retrieved.confidence:.2f}")

    # Check all actions
    print(f"\nTotal learned actions: {len(store)}")
    for a in store.list_all():
        print(f"  - {a.button}: {a.action_type} ({a.description})")

    print("\nDone!")
