"""What is this object, and which physics test would actually tell you something.

Separate from selection.py on purpose. Selection answers the agent's own loop and
its answer is persisted on the job; this answers a VIEWER asking about a mesh it
is already looking at, and nothing is written down. Same model, different caller.
"""

from __future__ import annotations

from typing import Final, Literal

from google.adk.agents import LlmAgent
from google.genai import types
from pydantic import BaseModel, Field

IDENTIFY_INSTRUCTION: Final = (
    "You are Rinne's identification step. You are shown one photograph of a single "
    "object that has just been reconstructed into a 3D mesh. Name it, size it, and "
    "say which physics test would actually reveal how it fails.\n"
    "\n"
    "tip - a lateral push near the top. Right for anything tall and narrow over a "
    "small footprint, and for anything visibly leaning.\n"
    "drop - released from 10 cm. Right for a compact object where the question is "
    "whether a knock unseats it.\n"
    "impact - released from 1.5 m. Right for something whose failure is a fall: "
    "fragile, top-heavy, or carried.\n"
    "load - weight on the top face. Right for a stack, a shelf, or anything whose "
    "failure mode is what sits on it.\n"
    "\n"
    "label names the object in two to four words, specifically: 'stainless kitchen "
    "scissors', not 'tool'.\n"
    "longest_dimension_meters is its longest side in METRES, from everyday knowledge "
    "of what it is. A charger adapter is about 0.07, a mug 0.12, a wine bottle 0.30, "
    "a laptop 0.35, a dining chair 0.9, a hatchback 4.0.\n"
    "material is what its bulk is made of, for mass.\n"
    "primary is the ONE test worth watching first. rationale is two plain sentences: "
    "why that test, and why one of the others tells you less about THIS object. "
    "Name the geometry you reasoned from. Never use emojis."
)


class IdentifyOutput(BaseModel):
    """Flat on purpose. A nested schema is one more thing Gemini can reject."""

    label: str = Field(description="The object, specifically, in two to four words.")
    longest_dimension_meters: float = Field(
        ge=0.01, le=5.0, description="Longest side in metres, from what the object is."
    )
    material: Literal["cardboard", "wood", "plastic", "metal", "glass", "fabric", "unknown"] = (
        Field(description="What its bulk is made of.")
    )
    primary: Literal["tip", "drop", "impact", "load"] = Field(
        description="The one test worth watching first."
    )
    rationale: str = Field(description="Two sentences naming the geometry. No emojis.")


def build_identify_agent(
    *,
    model: str,
    temperature: float,
    max_output_tokens: int,
    thinking_budget: int,
) -> LlmAgent:
    """A leaf, like triage and selection, for the same reason: no transfers."""
    return LlmAgent(
        name="rinne_identify",
        model=model,
        instruction=IDENTIFY_INSTRUCTION,
        output_schema=IdentifyOutput,
        output_key="identify",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        generate_content_config=types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            thinking_config=types.ThinkingConfig(thinking_budget=thinking_budget),
        ),
    )
