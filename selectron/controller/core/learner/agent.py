"""
ADK-powered learning agent for button action learning.

Uses Google's Agent Development Kit with Gemini's multimodal capabilities
to analyze screen recordings and extract actionable automation steps.
"""

import asyncio
import base64
import json
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from pathlib import Path

from ..emulator import GamepadButton
from .store import LearnedAction


@dataclass
class AnalysisResult:
    """Result of analyzing a screen recording."""
    success: bool
    action_type: str  # "click", "type", "key_combo", "scroll", "drag", "none"
    parameters: Dict[str, Any]
    description: str
    confidence: float
    raw_response: str = ""


class ButtonLearningAgent:
    """
    ADK agent that learns button actions from screen recordings.

    Analyzes sequences of screenshots captured during user demonstration
    to extract the action the user performed, then encodes it in a format
    that can be replayed.
    """

    SYSTEM_INSTRUCTION = '''You are a UI automation learning agent. Your task is to analyze
screen recordings (sequences of screenshots) and determine what action the user performed.

When shown screenshots, analyze:
1. What changed between frames (mouse movement, UI state changes)
2. What UI element the user interacted with (button, text field, menu, etc.)
3. What action was performed (click, double-click, type, scroll, key combo, drag)
4. The exact parameters needed to reproduce the action

Output your analysis as JSON with this structure:
{
    "action_type": "click|double_click|type|key_combo|scroll|drag|none",
    "parameters": {
        // For click/double_click: {"x": int, "y": int, "element_description": str}
        // For type: {"text": str, "target_element": str}
        // For key_combo: {"keys": ["cmd", "c"], "description": str}
        // For scroll: {"direction": "up|down|left|right", "amount": int}
        // For drag: {"start_x": int, "start_y": int, "end_x": int, "end_y": int}
        // For none: {}
    },
    "description": "Human-readable description of the action",
    "confidence": 0.0-1.0
}

If you cannot determine what action was performed, use action_type "none" with low confidence.
Focus on the most significant action in the recording - usually what happens near the cursor.'''

    def __init__(self, model: str = "gemini-2.0-flash"):
        """
        Initialize the learning agent.

        Args:
            model: Gemini model to use (default: gemini-2.0-flash for multimodal).
        """
        self.model = model
        self._agent = None
        self._runner = None
        self._session_service = None
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Lazily initialize the ADK components."""
        if self._initialized:
            return

        try:
            from google.adk.agents import Agent
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService

            self._agent = Agent(
                name='button_learner',
                model=self.model,
                instruction=self.SYSTEM_INSTRUCTION,
            )

            self._session_service = InMemorySessionService()
            self._runner = Runner(
                agent=self._agent,
                app_name='button_learner',
                session_service=self._session_service,
            )

            self._initialized = True

        except ImportError as e:
            raise ImportError(
                f"Google ADK required: pip install google-adk\n"
                f"Original error: {e}"
            )

    def _encode_frames(self, frames: List[bytes]) -> List[Dict[str, Any]]:
        """
        Encode frame data for the Gemini API.

        Args:
            frames: List of PNG image bytes.

        Returns:
            List of encoded frame objects for the API.
        """
        encoded = []
        for i, frame in enumerate(frames):
            encoded.append({
                "type": "image",
                "data": base64.b64encode(frame).decode('utf-8'),
                "mime_type": "image/png",
                "description": f"Frame {i+1} of {len(frames)}"
            })
        return encoded

    async def analyze_recording(
        self,
        frames: List[bytes],
        button: GamepadButton,
        context: str = "",
    ) -> LearnedAction:
        """
        Analyze a screen recording and extract the action.

        Args:
            frames: List of PNG screenshot bytes (captured during demonstration).
            button: The button that triggered this learning session.
            context: Optional context about what the user was trying to do.

        Returns:
            LearnedAction with the extracted action details.
        """
        await self._ensure_initialized()

        # Build the prompt
        prompt_parts = []

        # Add context
        if context:
            prompt_parts.append(f"Context: {context}")

        prompt_parts.append(
            f"The user pressed the '{button.name}' button and demonstrated an action. "
            f"Analyze these {len(frames)} sequential screenshots to determine what they did. "
            f"Focus on changes near the cursor and UI state changes."
        )

        # Sample frames if too many (Gemini has token limits)
        max_frames = 10
        if len(frames) > max_frames:
            # Take evenly spaced samples
            indices = [int(i * len(frames) / max_frames) for i in range(max_frames)]
            frames = [frames[i] for i in indices]
            prompt_parts.append(f"(Showing {max_frames} sampled frames from {len(frames)} total)")

        prompt_parts.append("\nAnalyze and output JSON:")

        try:
            from google.genai import types

            # Create session
            session = await self._session_service.create_session(
                app_name='button_learner',
                user_id='learning_system',
            )

            # Build multimodal message
            parts = [types.Part(text="\n".join(prompt_parts))]

            for frame in frames:
                parts.append(types.Part(
                    inline_data=types.Blob(
                        mime_type="image/png",
                        data=base64.b64encode(frame).decode()
                    )
                ))

            message = types.Content(role='user', parts=parts)

            # Run agent and collect response
            response_text = ""
            async for event in self._runner.run_async(
                user_id='learning_system',
                session_id=session.id,
                new_message=message,
            ):
                if hasattr(event, 'content') and event.content:
                    if hasattr(event.content, 'parts'):
                        for part in event.content.parts:
                            if hasattr(part, 'text') and part.text:
                                response_text += part.text

            # Parse the response
            result = self._parse_response(response_text)

            return LearnedAction(
                button=button.name,
                action_type=result.action_type,
                parameters=result.parameters,
                description=result.description,
                confidence=result.confidence,
                recorded_frames=len(frames),
                analysis_summary=result.raw_response[:500],  # Truncate for storage
            )

        except Exception as e:
            # Return a failed action on error
            return LearnedAction(
                button=button.name,
                action_type="none",
                parameters={"error": str(e)},
                description=f"Analysis failed: {e}",
                confidence=0.0,
                recorded_frames=len(frames),
                analysis_summary=f"Error: {e}",
            )

    def _parse_response(self, response: str) -> AnalysisResult:
        """
        Parse the agent's JSON response.

        Args:
            response: Raw text response from the agent.

        Returns:
            AnalysisResult with parsed data.
        """
        # Try to extract JSON from the response
        try:
            # Find JSON in the response (might be wrapped in markdown code blocks)
            json_str = response
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                json_str = response[start:end].strip()
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                json_str = response[start:end].strip()

            # Try to find raw JSON object
            if json_str.startswith('{'):
                pass
            else:
                # Find first { and last }
                start = response.find('{')
                end = response.rfind('}') + 1
                if start >= 0 and end > start:
                    json_str = response[start:end]

            data = json.loads(json_str)

            return AnalysisResult(
                success=True,
                action_type=data.get("action_type", "none"),
                parameters=data.get("parameters", {}),
                description=data.get("description", ""),
                confidence=float(data.get("confidence", 0.5)),
                raw_response=response,
            )

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            # Failed to parse - return uncertain result
            return AnalysisResult(
                success=False,
                action_type="none",
                parameters={"parse_error": str(e)},
                description=f"Could not parse agent response",
                confidence=0.0,
                raw_response=response,
            )


class MockLearningAgent:
    """
    Mock learning agent for testing without ADK/Gemini.

    Returns predetermined responses for testing the learning flow.
    """

    def __init__(self):
        self.call_count = 0
        self.mock_responses = [
            LearnedAction(
                button="A",
                action_type="click",
                parameters={"x": 500, "y": 300, "element_description": "Submit button"},
                description="Click the Submit button",
                confidence=0.9,
                recorded_frames=30,
                analysis_summary="Mock: Detected click on button element",
            ),
            LearnedAction(
                button="B",
                action_type="key_combo",
                parameters={"keys": ["cmd", "s"], "description": "Save shortcut"},
                description="Press Cmd+S to save",
                confidence=0.85,
                recorded_frames=25,
                analysis_summary="Mock: Detected keyboard shortcut",
            ),
        ]

    async def analyze_recording(
        self,
        frames: List[bytes],
        button: GamepadButton,
        context: str = "",
    ) -> LearnedAction:
        """Return a mock analysis result."""
        await asyncio.sleep(0.5)  # Simulate processing time

        # Cycle through mock responses
        response = self.mock_responses[self.call_count % len(self.mock_responses)]
        self.call_count += 1

        # Update with actual button
        return LearnedAction(
            button=button.name,
            action_type=response.action_type,
            parameters=response.parameters,
            description=response.description,
            confidence=response.confidence,
            recorded_frames=len(frames),
            analysis_summary=response.analysis_summary,
        )


# === Demo ===

async def demo():
    """Demo the learning agent with mock data."""
    print("Learning Agent Demo")
    print("=" * 40)

    # Use mock agent for demo
    agent = MockLearningAgent()

    # Simulate frames (just empty bytes for demo)
    mock_frames = [b"mock_frame"] * 30

    # Analyze for button A
    print("\nAnalyzing button A press...")
    result = await agent.analyze_recording(
        frames=mock_frames,
        button=GamepadButton.A,
        context="User was filling out a form",
    )

    print(f"Result:")
    print(f"  Action: {result.action_type}")
    print(f"  Parameters: {result.parameters}")
    print(f"  Description: {result.description}")
    print(f"  Confidence: {result.confidence:.0%}")

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(demo())
