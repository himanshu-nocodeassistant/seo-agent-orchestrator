from dataclasses import replace

import pytest

from agent.webflow.approvals import (
    ApplyDecision,
    InvalidStateTransition,
    Operation,
    Proposal,
    ProposalState,
    apply_decision,
    can_apply,
    compare_snapshot,
    requires_approval,
    transition,
)


def make_proposal(**changes):
    values = {
        "proposal_id": "proposal-1234567890",
        "operation": Operation.UPDATE,
        "resource_id": "item-1234567890",
        "name": "A very long, complete title that must not be shortened",
        "payload": {"content": "full body", "nested": {"keep": True}},
        "snapshot": {"id": "item-1234567890", "version": 7},
    }
    return Proposal(**(values | changes))


def test_operation_and_proposal_preserve_values():
    proposal = make_proposal()

    assert {Operation.CREATE.value, Operation.UPDATE.value, Operation.PUBLISH.value} == {
        "create",
        "update",
        "publish",
    }
    assert proposal.name == "A very long, complete title that must not be shortened"
    assert proposal.payload["nested"] == {"keep": True}


@pytest.mark.parametrize("operation", list(Operation))
def test_all_webflow_mutations_require_approval(operation):
    assert requires_approval(operation) is True


def test_reads_do_not_require_approval():
    assert requires_approval("read") is False
    assert requires_approval("list") is False


def test_state_transitions_are_validated():
    assert transition(ProposalState.DRAFT, ProposalState.PENDING_APPROVAL) == ProposalState.PENDING_APPROVAL
    assert transition(ProposalState.PENDING_APPROVAL, ProposalState.APPROVED) == ProposalState.APPROVED
    assert transition(ProposalState.APPROVED, ProposalState.APPLIED) == ProposalState.APPLIED

    with pytest.raises(InvalidStateTransition):
        transition(ProposalState.DRAFT, ProposalState.APPLIED)


def test_stale_snapshot_comparison_compares_full_json_values():
    expected = {"version": 7, "fields": {"body": "x"}}
    assert compare_snapshot(expected, {"version": 7, "fields": {"body": "x"}}) is False
    assert compare_snapshot(expected, {"version": 8, "fields": {"body": "x"}}) is True
    assert compare_snapshot(expected, {"version": 7, "fields": {"body": "changed"}}) is True


def test_apply_decision_is_idempotent_for_same_applied_proposal():
    proposal = make_proposal(state=ProposalState.APPROVED)
    applied = replace(proposal, state=ProposalState.APPLIED)

    assert can_apply(proposal) is True
    assert can_apply(applied) is False
    assert apply_decision(applied, current_snapshot=proposal.snapshot) == ApplyDecision.ALREADY_APPLIED


def test_apply_decision_rejects_unapproved_and_stale_proposals():
    pending = make_proposal(state=ProposalState.PENDING_APPROVAL)
    assert apply_decision(pending, current_snapshot=pending.snapshot) == ApplyDecision.NOT_APPROVED

    approved = replace(pending, state=ProposalState.APPROVED)
    assert apply_decision(approved, current_snapshot={"id": "item-1234567890", "version": 8}) == ApplyDecision.STALE
    assert apply_decision(approved, current_snapshot=approved.snapshot) == ApplyDecision.APPLY
