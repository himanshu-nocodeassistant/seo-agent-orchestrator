"""Pure domain rules for approving Webflow mutations.

This module deliberately has no Webflow, database, or HTTP dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, TypeAlias


JSONValue: TypeAlias = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]
JSONPayload: TypeAlias = Mapping[str, JSONValue]


class Operation(str, Enum):
    """A Webflow operation which can be proposed for execution."""

    CREATE = "create"
    UPDATE = "update"
    PUBLISH = "publish"


class ProposalState(str, Enum):
    """Lifecycle states for a proposal."""

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    AWAITING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"


class ApplyDecision(str, Enum):
    """Result of deciding whether an approved proposal may be applied."""

    APPLY = "apply"
    NOT_APPROVED = "not_approved"
    STALE = "stale"
    STALE_SNAPSHOT = "stale"
    ALREADY_APPLIED = "already_applied"
    NOOP = "already_applied"


class InvalidStateTransition(ValueError):
    """Raised when a proposal is moved between unsupported states."""


@dataclass(frozen=True)
class Proposal:
    """A complete, typed proposal for one Webflow mutation.

    Strings and JSON payloads are retained as supplied. No truncation or
    serialization is performed by this domain object.
    """

    proposal_id: str
    operation: Operation
    resource_id: str | None
    name: str
    payload: JSONPayload
    snapshot: JSONPayload
    state: ProposalState = ProposalState.DRAFT


_READ_OPERATIONS = frozenset({"read", "list", "get", "retrieve"})
_VALID_TRANSITIONS = {
    ProposalState.DRAFT: frozenset({ProposalState.PENDING_APPROVAL}),
    ProposalState.PENDING_APPROVAL: frozenset({ProposalState.APPROVED, ProposalState.REJECTED}),
    ProposalState.APPROVED: frozenset({ProposalState.APPLIED}),
    ProposalState.REJECTED: frozenset(),
    ProposalState.APPLIED: frozenset(),
}


def requires_approval(operation: Operation | str) -> bool:
    """Return whether an operation must pass human approval.

    All supported Webflow mutations require approval. Read-like operation
    names return ``False`` so callers can use this function at the policy
    boundary without creating proposals for reads.
    """

    value = operation.value if isinstance(operation, Operation) else operation.lower()
    return value not in _READ_OPERATIONS


def transition(current: ProposalState, target: ProposalState) -> ProposalState:
    """Validate and return a proposal state transition."""

    if target not in _VALID_TRANSITIONS[current]:
        raise InvalidStateTransition(f"cannot transition proposal from {current.value} to {target.value}")
    return target


def compare_snapshot(expected: JSONPayload, current: JSONPayload) -> bool:
    """Return ``True`` when the current Webflow snapshot is stale."""

    return expected != current


def is_stale(expected: JSONPayload, current: JSONPayload) -> bool:
    """Alias for :func:`compare_snapshot` with a predicate-oriented name."""

    return compare_snapshot(expected, current)


def can_apply(proposal: Proposal) -> bool:
    """Return whether the proposal is approved and has not been applied."""

    return proposal.state is ProposalState.APPROVED


def apply_decision(proposal: Proposal, current_snapshot: JSONPayload) -> ApplyDecision:
    """Make an idempotent, side-effect-free decision about applying a proposal."""

    if proposal.state is ProposalState.APPLIED:
        return ApplyDecision.ALREADY_APPLIED
    if proposal.state is not ProposalState.APPROVED:
        return ApplyDecision.NOT_APPROVED
    if compare_snapshot(proposal.snapshot, current_snapshot):
        return ApplyDecision.STALE
    return ApplyDecision.APPLY


def decide_apply(proposal: Proposal, current_snapshot: JSONPayload) -> ApplyDecision:
    """Alias for :func:`apply_decision`."""

    return apply_decision(proposal, current_snapshot)


__all__ = [
    "ApplyDecision",
    "InvalidStateTransition",
    "JSONPayload",
    "JSONValue",
    "Operation",
    "Proposal",
    "ProposalState",
    "apply_decision",
    "can_apply",
    "compare_snapshot",
    "decide_apply",
    "is_stale",
    "requires_approval",
    "transition",
]
