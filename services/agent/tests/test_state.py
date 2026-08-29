from __future__ import annotations

from datetime import UTC, datetime

import pytest

from rinne_agent.contracts import AgentJob
from rinne_agent.contracts.agent_job import JobActor, JobState
from rinne_agent.state import (
    TERMINAL,
    TRANSITIONS,
    IllegalTransitionError,
    can_transition,
    fail,
    transition,
)

STAMP = datetime(2026, 8, 29, 4, 20, tzinfo=UTC)


def job(state: JobState = JobState.queued, *, decisions: int = 1) -> AgentJob:
    return AgentJob.model_validate(
        {
            "schemaVersion": 1,
            "jobId": "scan-9f2c41ab77d05e13",
            "state": state,
            "attempts": 1,
            "createdAt": STAMP,
            "updatedAt": STAMP,
            "source": {
                "bucket": "rinne-scans-rinnehackathon",
                "object": "scan-queue/desk.jpg",
                "generation": "1756400000000000",
                "contentType": "image/png",
                "sizeBytes": 128,
                "receivedAt": STAMP,
            },
            "decisions": [
                {
                    "at": STAMP,
                    "state": JobState.queued,
                    "actor": JobActor.ingest,
                    "summary": f"entry {index}",
                }
                for index in range(decisions)
            ],
        }
    )


def test_every_contract_state_has_a_row() -> None:
    """No implicit states. The enum is generated from the schema, so this is the
    check that the table and the contract cannot drift apart."""
    assert set(TRANSITIONS) == set(JobState)
    assert len(JobState) == 10


def test_the_three_terminal_states_are_exactly_the_expected_ones() -> None:
    assert sorted(state.value for state in TERMINAL) == [
        "done",
        "failed",
        "skipped_low_risk",
    ]


@pytest.mark.parametrize("state", sorted(TERMINAL, key=lambda item: item.value))
def test_terminal_states_have_no_outgoing_edges(state: JobState) -> None:
    assert TRANSITIONS[state] == frozenset()


@pytest.mark.parametrize("state", [s for s in JobState if s not in TERMINAL])
def test_failed_is_reachable_from_every_non_terminal_state(state: JobState) -> None:
    assert can_transition(state, JobState.failed)


def test_skipped_low_risk_is_reachable_and_terminal() -> None:
    """It is an outcome, not a failure, and section 0c records it as the most
    common one."""
    assert can_transition(JobState.queued, JobState.skipped_low_risk)
    assert JobState.skipped_low_risk in TERMINAL


def test_gated_is_declared_but_nothing_in_this_build_reaches_it() -> None:
    """The Gemma tier-0 gate was cut. The state stays so the cascade is still
    describable; queued -> gated -> triaged is the shape the ADR documents."""
    assert can_transition(JobState.queued, JobState.gated)
    assert can_transition(JobState.gated, JobState.triaged)


def test_inconclusive_has_somewhere_to_go_before_day_five_needs_it() -> None:
    """SimulationResult.outcome.verdict = inconclusive is the physics refusing
    to guess. Day 5 escalates on it, and the edge already exists."""
    assert can_transition(JobState.simulating, JobState.awaiting_verification)
    assert can_transition(JobState.awaiting_verification, JobState.refitting)
    assert can_transition(JobState.refitting, JobState.simulating)


def test_a_legal_transition_records_a_decision_entry() -> None:
    moved = transition(
        job(),
        target=JobState.triaged,
        actor=JobActor.triage,
        summary="Flash decided this warrants a physics review.",
        model="gemini-3.5-flash",
        confidence=0.95,
        latency_ms=1840,
        at=STAMP,
    )
    assert moved.state is JobState.triaged
    assert moved.decisions[-1].actor is JobActor.triage
    assert moved.decisions[-1].model == "gemini-3.5-flash"
    assert moved.updated_at == STAMP


def test_transition_does_not_mutate_its_input() -> None:
    original = job()
    transition(original, target=JobState.triaged, actor=JobActor.triage, summary="x")
    assert original.state is JobState.queued
    assert len(original.decisions) == 1


def test_an_illegal_edge_raises_rather_than_being_silently_allowed() -> None:
    with pytest.raises(IllegalTransitionError):
        transition(job(), target=JobState.done, actor=JobActor.report, summary="skip ahead")


def test_a_terminal_state_cannot_transition_at_all() -> None:
    with pytest.raises(IllegalTransitionError):
        transition(
            job(JobState.skipped_low_risk),
            target=JobState.triaged,
            actor=JobActor.triage,
            summary="reopen",
        )


def test_fail_records_error_and_last_good_state() -> None:
    failed = fail(
        job(JobState.simulating),
        rule="the physics service is unavailable",
        retryable=True,
        actor=JobActor.physics,
        at=STAMP,
    )
    assert failed.state is JobState.failed
    assert failed.last_good_state is JobState.simulating
    assert failed.error is not None
    assert failed.error.rule == "the physics service is unavailable"
    assert failed.error.retryable is True
    assert failed.error.actor is JobActor.physics


def test_fail_refuses_a_terminal_job() -> None:
    with pytest.raises(IllegalTransitionError):
        fail(job(JobState.done), rule="too late", retryable=False, actor=JobActor.report)


def test_the_decision_trail_is_bounded_and_keeps_the_newest() -> None:
    crowded = job(decisions=24)
    moved = transition(crowded, target=JobState.triaged, actor=JobActor.triage, summary="newest")
    assert len(moved.decisions) == 24
    assert moved.decisions[-1].summary == "newest"
    assert moved.decisions[0].summary == "entry 1"


def test_a_long_summary_is_truncated_rather_than_rejected() -> None:
    moved = transition(job(), target=JobState.triaged, actor=JobActor.triage, summary="x" * 400)
    assert len(moved.decisions[-1].summary) == 240
