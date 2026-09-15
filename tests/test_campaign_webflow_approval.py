"""Campaign publishing must use the same Webflow proposal gate."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_campaign_publisher_saves_proposal_and_pauses(monkeypatch):
    import agent.api.main as main_module
    from agent.orchestrator import run_campaign_orchestration

    monkeypatch.setenv("WEBFLOW_ACCESS_TOKEN", "test-token")
    plan = {
        "campaign_goal": "Publish one post",
        "phases": [
            {
                "phase": "researcher",
                "task_title": "Research post",
                "task_description": "Find keywords.",
                "execution_type": "campaign_researcher",
                "depends_on": [],
            },
            {
                "phase": "writer",
                "task_title": "Write post",
                "task_description": "Write the post.",
                "execution_type": "campaign_draft_writer",
                "depends_on": ["researcher"],
            },
            {
                "phase": "publisher",
                "task_title": "Publish post",
                "task_description": "Publish the post to Webflow.",
                "execution_type": "campaign_publisher",
                "depends_on": ["writer"],
            },
        ],
    }
    outputs = iter([
        SimpleNamespace(result_text=f"```json\n{json.dumps(plan)}\n```", session_id="s0"),
        SimpleNamespace(
            result_text=(
                "Keyword: automation. Source: https://example.com\n"
                "## Summary for Next Phase\nResearch ready.\n## End Summary"
            ),
            session_id="s1",
        ),
        SimpleNamespace(
            result_text=(
                "Title: Post\nURL slug: post\nWord count: 100\n"
                "Webflow status: manual-only\n"
                "<!-- CHANGE_LOG\n{}\n-->\n"
                "## Summary for Next Phase\nDraft ready.\n## End Summary"
            ),
            session_id="s2",
        ),
        SimpleNamespace(
            result_text=(
                "Webflow status: pending approval\n"
                "<!-- CHANGE_LOG\n{}\n-->\n"
                "```json\n"
                '{"webflow_proposal":{"operation":"publish","resource_id":"item-1",'
                '"snapshot":{"id":"item-1","version":1},"payload":{}}}\n'
                "```"
            ),
            session_id="s3",
        ),
    ])

    async def fake_run(*args, **kwargs):
        return next(outputs)

    with patch("agent.api.helpers._run_agent_prompt", side_effect=fake_run):
        db = main_module.get_db_session()
        try:
            now = main_module.datetime.utcnow().isoformat()
            parent = main_module.TaskModel(
                title="Publish campaign",
                description="Publish one post",
                execution_type="orchestrate_seo_campaign",
                status="in_progress",
                approved_at=now,
                created_at=now,
                updated_at=now,
            )
            db.add(parent)
            db.commit()
            db.refresh(parent)
            run = main_module._create_run(
                db, parent, "manual_execute", "orchestrate_seo_campaign"
            )

            await run_campaign_orchestration(db, parent, run)

            child = db.query(main_module.TaskModel).filter_by(
                parent_task_id=parent.id,
                execution_type="campaign_publisher",
            ).one()
            proposal = db.query(main_module.WebflowProposalModel).filter_by(
                task_id=child.id,
            ).one()
            state = db.query(main_module.OrchestrationStateModel).filter_by(
                orchestrator_run_id=run.run_id,
            ).one()
            assert proposal.status == "pending_approval"
            assert state.status == "awaiting_approval"
            assert run.status == "awaiting_approval"
        finally:
            db.close()
