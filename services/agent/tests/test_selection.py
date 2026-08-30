from __future__ import annotations

import pytest
from google.adk.agents import LlmAgent
from pydantic import ValidationError

from rinne_agent.agents.runtime import StubSelector, build_selector
from rinne_agent.agents.selection import (
    SELECTION_INSTRUCTION,
    SelectionOutput,
    build_selection_agent,
)


def agent() -> LlmAgent:
    return build_selection_agent(
        model="gemini-3.5-flash", temperature=0.0, max_output_tokens=512, thinking_budget=0
    )


def test_the_selection_agent_is_a_leaf_with_structured_output() -> None:
    built = agent()
    assert built.name == "rinne_selection"
    assert built.output_schema is SelectionOutput
    assert built.output_key == "selection"
    assert built.disallow_transfer_to_parent is True
    assert built.disallow_transfer_to_peers is True


def test_thinking_stays_disabled_on_the_second_agent_too() -> None:
    config = agent().generate_content_config
    assert config is not None
    assert config.thinking_config is not None
    assert config.thinking_config.thinking_budget == 0


def test_the_instruction_covers_every_test_kind_and_forbids_emojis() -> None:
    for kind in ("tip", "load", "drop", "none"):
        assert f"{kind} -" in SELECTION_INSTRUCTION
    assert "Never use emojis" in SELECTION_INSTRUCTION
    # Forces and heights are the service's measurement, not the model's guess.
    assert "Do not estimate mass, force or dimensions" in SELECTION_INSTRUCTION


def test_the_model_is_asked_for_a_choice_and_nothing_it_cannot_know() -> None:
    assert set(SelectionOutput.model_fields) == {"kind", "confidence", "rationale"}


@pytest.mark.parametrize("kind", ["tip", "load", "drop", "none"])
def test_every_legal_kind_validates(kind: str) -> None:
    assert (
        SelectionOutput.model_validate({"kind": kind, "confidence": 0.8, "rationale": "x"}).kind
        == kind
    )


def test_an_invented_test_kind_is_refused() -> None:
    with pytest.raises(ValidationError):
        SelectionOutput.model_validate({"kind": "shake", "confidence": 0.8, "rationale": "x"})


async def test_the_stub_selector_is_offline_and_says_so() -> None:
    outcome = await StubSelector(kind="drop").select(
        job_id="scan-1", image=b"", mime_type="image/png", shape="irregular"
    )
    assert outcome.model == "stub-selection"
    assert outcome.output.kind == "drop"
    assert "No model was called" in outcome.output.rationale


def test_flash_mode_without_an_agent_refuses_to_build() -> None:
    with pytest.raises(RuntimeError):
        build_selector(
            mode="flash",
            agent=None,
            app_name="rinne-agent",
            model="gemini-3.5-flash",
            timeout_seconds=60.0,
        )
