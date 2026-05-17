"""Workflow plane (spec §11).

v1 ships plain async orchestrators. They are Temporal-shaped (idempotent
activities, bounded retry, signals for approvals) so swapping them for actual
Temporal `@workflow.defn` classes is mechanical.
"""

from avengers.workflows.approval import (
    ApprovalQueue,
    ApprovalTimeoutError,
    request_approval,
)
from avengers.workflows.deep_dive import run_deep_dive
from avengers.workflows.morning_brief import run_morning_brief

__all__ = [
    "ApprovalQueue",
    "ApprovalTimeoutError",
    "request_approval",
    "run_deep_dive",
    "run_morning_brief",
]
