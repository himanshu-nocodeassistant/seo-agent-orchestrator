# Agent Safety Hardening Plan

Fixes identified from the safety audit. Implemented in order of risk: loop protection
first, then permissions, then hallucination guards. Each change is a separate commit
following red/green TDD.

---

## Changes

### Fix 1 — G3.1: Raise on unknown execution_type (runtime_profiles.py)
**File:** `agent/runtime_profiles.py`
**Change:** `get_execution_profile` raises `ValueError` for unrecognised strings instead
of silently falling back to `manual`.
**Test:** `tests/test_safety_hardening.py::TestGetExecutionProfile`

### Fix 2 — G3.3: Remove Bash from default AgentConfig tool list (config.py)
**File:** `agent/config.py`
**Change:** Remove `"Bash"` from the `allowed_tools` default factory. Bash is overwritten
by `_build_runtime_config` before any real run, but the default unsafe list is still
reached by direct `execute_task` callers (CLI, tests).
**Test:** `tests/test_safety_hardening.py::TestAgentConfigDefaults`

### Fix 3 — G1.2: Add max_total_seconds wall-clock cap to _run_with_retry (orchestrator.py)
**File:** `agent/orchestrator.py`
**Change:** Add `max_total_seconds: Optional[float] = None` parameter to
`_run_with_retry`. Check `time.monotonic()` before each attempt; raise `RuntimeError`
if the deadline is exceeded.
**Test:** `tests/test_safety_hardening.py::TestRunWithRetryWallClock`

### Fix 4 — G1.1: Wrap run_campaign_orchestration with asyncio.wait_for (main.py)
**File:** `agent/api/main.py`
**Change:** Wrap the `await run_campaign_orchestration(...)` call at line ~2097 with
`asyncio.wait_for(timeout=CAMPAIGN_TIMEOUT_SECONDS)`. Env var
`CAMPAIGN_TIMEOUT_SECONDS` defaults to `5400` (6 tiers × 900s).
**Test:** `tests/test_safety_hardening.py::TestCampaignTimeout`

### Fix 5 — G2.4: Validator failure stops downstream phases (orchestrator.py)
**File:** `agent/orchestrator.py`
**Change:** In `_dispatch_phase`, check `child_validation.status` after running the
validator. If `"failed"`, raise `RuntimeError` so the orchestrator tier treats it as
a phase failure and halts the campaign.
**Test:** `tests/test_safety_hardening.py::TestValidatorFailureStopsPipeline`

### Fix 6 — G2.1: Stronger research output validator (runtime_profiles.py)
**File:** `agent/runtime_profiles.py`
**Change:** Replace `_validate_non_empty` on `research` and `campaign_researcher`
profiles with `_validate_research_output`. Requires at least one `https://` URL and
one keyword-related token in the output.
**Test:** `tests/test_safety_hardening.py::TestResearchValidator`

---

## Order of implementation

1. G3.1 — smallest change, zero risk, catches a whole class of silent bugs
2. G3.3 — one-liner, removes ambient Bash access from the default path
3. G1.2 — adds `max_total_seconds` to retry; purely additive, no behaviour change
       if `max_total_seconds=None` (default)
4. G1.1 — adds campaign-level timeout; requires G1.2 to be in place first so the
       per-phase timeout also has the wall-clock cap
5. G2.4 — makes validators authoritative; must come before G2.1 so the new research
       validator can actually stop the pipeline on failure
6. G2.1 — strengthens research validators; safe last because G2.4 is already wired

## Deferred (require product decisions or separate design work)
- G2.2 — grounding requirement (needs prompt-level + validator changes across profiles)
- G2.3 — approval gate before publisher (Kanban UI change required)
- G3.2 — split campaign_content_writer into draft-only + publish-only profiles
- G3.4 — PostToolUse hook audit log
