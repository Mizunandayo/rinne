"""Section 7 step 2. Which physics test actually matters for this shape."""

from __future__ import annotations

from typing import Final, Literal

from google.adk.agents import LlmAgent
from google.genai import types
from pydantic import BaseModel, Field

SELECTION_INSTRUCTION: Final = (
    "You are Rinne's test-selection step. Triage has already decided this object "
    "warrants a physics review and has classified its shape. Choose the ONE test "
    "that would actually reveal how it fails.\n"
    "\n"
    "tip - a lateral push near the top. Right for anything tall and narrow over a "
    "small footprint, and for anything visibly leaning.\n"
    "load - weight placed on the top face. Right for a stack, a shelf, or anything "
    "whose failure mode is what sits on it.\n"
    "drop - released from a short height. Right for an irregular or compact object "
    "where the question is whether it survives being knocked off.\n"
    "none - nothing here is worth simulating.\n"
    "\n"
    "confidence is your certainty in THIS choice. rationale is one or two plain "
    "sentences naming the geometry you chose from.\n"
    "\n"
    "label names the object in two or three words.\n"
    "longest_dimension_meters is its longest side in METRES, from everyday "
    "knowledge of what the object is. Nothing downstream can recover scale from "
    "a single photograph, so this number decides the object's size, its mass and "
    "every force applied to it. A charger adapter is about 0.07, a mug 0.12, a "
    "wine bottle 0.30, a laptop 0.35, a dining chair 0.9. Never use emojis. Do "
    "not estimate mass or force; those are derived from this number."
)


class SelectionOutput(BaseModel):
    """What the model returns. Forces stay derived; scale cannot be, so it is asked for."""

    kind: Literal["tip", "load", "drop", "none"] = Field(description="The single test to run.")
    confidence: float = Field(ge=0.0, le=1.0, description="Certainty in this choice.")
    rationale: str = Field(description="One or two sentences. No emojis.")
    # Only ge/le here: gt emits exclusiveMinimum, and Gemini's Schema type rejects
    # any key it does not know, which fails the whole call rather than the field.
    label: str = Field(description="The object, in a few words.")
    longest_dimension_meters: float = Field(
        ge=0.01, le=5.0, description="Longest side in metres, from what the object is."
    )


def build_selection_agent(
    *,
    model: str,
    temperature: float,
    max_output_tokens: int,
    thinking_budget: int,
) -> LlmAgent:
    """A leaf, like triage: transfer would let the model route round the state machine."""
    return LlmAgent(
        name="rinne_selection",
        model=model,
        instruction=SELECTION_INSTRUCTION,
        output_schema=SelectionOutput,
        output_key="selection",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        generate_content_config=types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            thinking_config=types.ThinkingConfig(thinking_budget=thinking_budget),
        ),
    )
