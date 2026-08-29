from __future__ import annotations

import pytest
from google.adk.agents import LlmAgent

from rinne_agent.agents.runtime import StubTriager, build_triager
from rinne_agent.agents.triage import (
    TRIAGE_INSTRUCTION,
    TriageOutput,
    build_triage_agent,
    strip_emojis,
)


def test_the_agent_is_a_leaf_with_structured_output() -> None:
    agent = build_triage_agent(
        model="gemini-3.5-flash", temperature=0.0, max_output_tokens=512, thinking_budget=0
    )
    assert isinstance(agent, LlmAgent)
    assert agent.model == "gemini-3.5-flash"
    assert agent.output_schema is TriageOutput
    assert agent.output_key == "triage"
    # A leaf. Transfer would let the model route itself somewhere the state
    # machine never sanctioned.
    assert agent.disallow_transfer_to_parent is True
    assert agent.disallow_transfer_to_peers is True


def test_thinking_is_disabled_by_default() -> None:
    """Gemini 3.5 Flash draws thinking tokens from the same budget as the
    answer. Measured: 16 output tokens, 12 spent thinking, no content at all."""
    agent = build_triage_agent(
        model="gemini-3.5-flash", temperature=0.0, max_output_tokens=512, thinking_budget=0
    )
    config = agent.generate_content_config
    assert config is not None
    assert config.thinking_config is not None
    assert config.thinking_config.thinking_budget == 0
    assert config.temperature == 0.0


def test_the_instruction_forbids_emojis_and_test_selection() -> None:
    # Section 11 requires the instruction to say it; strip_emojis enforces it.
    assert "Never use emojis" in TRIAGE_INSTRUCTION
    # Test selection is Day 5. Triage classifies the shape and stops.
    assert "Do not choose a physics test" in TRIAGE_INSTRUCTION


def test_the_output_schema_asks_the_model_for_nothing_it_cannot_know() -> None:
    fields = set(TriageOutput.model_fields)
    assert fields == {"review", "shape", "confidence", "rationale"}
    # The model never asserts which model it was, how long it took, or on what
    # basis - the service measures all three.
    assert "model" not in fields
    assert "latencyMs" not in fields


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("A tall narrow object.", "A tall narrow object."),
        ("Looks unstable \U0001f632", "Looks unstable "),
        ("✅ stable", " stable"),
        ("café shelf", "café shelf"),
    ],
)
def test_emojis_are_stripped_and_accents_are_not(raw: str, expected: str) -> None:
    assert strip_emojis(raw) == expected


def test_a_confidence_outside_zero_to_one_is_refused() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TriageOutput.model_validate(
            {"review": True, "shape": "stack", "confidence": 1.4, "rationale": "x"}
        )


def test_an_unknown_shape_is_refused() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TriageOutput.model_validate(
            {"review": True, "shape": "spherical", "confidence": 0.5, "rationale": "x"}
        )


async def test_the_stub_triager_is_offline_and_says_so() -> None:
    result = await StubTriager().triage(job_id="scan-1", image=b"\x89PNG", mime_type="image/png")
    assert result.model == "stub-triage"
    assert "No model was called" in result.output.rationale


def test_flash_mode_without_an_agent_refuses_to_build() -> None:
    """There is no fallback FROM flash TO stub. A misconfigured revision fails
    at startup rather than quietly answering with a canned decision."""
    with pytest.raises(RuntimeError):
        build_triager(
            mode="flash",
            agent=None,
            app_name="rinne-agent",
            model="gemini-3.5-flash",
            timeout_seconds=60.0,
        )
