"""Tests for extracting complete Webflow proposals from agent output."""

from agent.webflow.proposal_parser import extract_webflow_proposal


def test_extracts_typed_proposal_without_shortening_content():
    long_body = "body " * 2000
    output = (
        "Final draft\n```json\n"
        + '{"webflow_proposal":{"operation":"update","resource_id":"item-1",'
        + '"snapshot":{"version":1},"payload":{"fieldData":{"content":'
        + repr(long_body).replace("'", '"')
        + "}}}}\n```"
    )

    proposal = extract_webflow_proposal(output)

    assert proposal is not None
    assert proposal["operation"] == "update"
    assert proposal["payload"]["fieldData"]["content"] == long_body


def test_missing_or_invalid_proposal_returns_none():
    assert extract_webflow_proposal("No proposal") is None
    assert extract_webflow_proposal("```json\n{\"webflow_proposal\": {}}\n```") is None
