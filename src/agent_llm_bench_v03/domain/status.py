"""Status enumeration for V0.3 benchmark runs."""

from enum import Enum


class RunStatus(str, Enum):
    """Allowed status values for suite and benchmark runs."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    TIMEOUT = "timeout"
    FAILED = "failed"
    SKIPPED = "skipped"
    ABORTED = "aborted"
    BUDGET_EXHAUSTED = "budget_exhausted"


# Allowed status transitions
STATUS_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.QUEUED: {RunStatus.RUNNING, RunStatus.SKIPPED},
    RunStatus.RUNNING: {
        RunStatus.COMPLETED,
        RunStatus.PARTIAL,
        RunStatus.TIMEOUT,
        RunStatus.FAILED,
        RunStatus.ABORTED,
        RunStatus.BUDGET_EXHAUSTED,
    },
    # Terminal states have no outgoing transitions
    RunStatus.COMPLETED: set(),
    RunStatus.PARTIAL: set(),
    RunStatus.TIMEOUT: set(),
    RunStatus.FAILED: set(),
    RunStatus.SKIPPED: set(),
    RunStatus.ABORTED: set(),
    RunStatus.BUDGET_EXHAUSTED: set(),
}


def can_transition(from_status: RunStatus, to_status: RunStatus) -> bool:
    """Check if a status transition is allowed."""
    return to_status in STATUS_TRANSITIONS.get(from_status, set())


def validate_transition(from_status: RunStatus, to_status: RunStatus) -> None:
    """Validate and raise on invalid status transitions."""
    if not can_transition(from_status, to_status):
        raise ValueError(
            f"Invalid status transition: {from_status.value} -> {to_status.value}"
        )
