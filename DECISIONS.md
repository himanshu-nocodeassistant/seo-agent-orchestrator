# Technical Decisions

Claude and Codex were heavily used for the coding part of the project, but technical and architectural decisions were also involved. 

This document covers the decisions made by me, and are written by Claude.

---

## 2026-05-25 — Building a Multi-Agent Orchestrator

### The Problem

The original SEOAgent did everything. Audit, content, research—all crammed into one agent. This worked fine when there were 2-3 things to do. But once I hit 10+ skills and multi-phase workflows (like a 6-phase SEO impact review), the output began to degrade.

I couldn't tell what was running. If something broke mid-pipeline, I'd have no idea where. And every new feature required touching the same giant agent class.

### What I Did

Split it into specialists:
- `ResearchAgent` handles web research and keyword analysis (tools: WebSearch, WebFetch)
- `ContentAgent` handles copywriting and content generation (tools: Read, Write, Edit, Skill)
- `AnalyticsAgent` handles SEO impact review and GSC analysis (tools: Read, WebFetch, Bash—read-only)
- `OrchestratorAgent` routes tasks to the right specialists based on what you're trying to do

Each specialist has exactly the tools it needs—nothing more. Research doesn't have write access. Analytics can't modify anything. This isn't paranoia; it's just good practice.

I also added progress tracking: after each stage, the system posts a comment to Kanban (`🔄 / ✅ / ❌`). This way you can see exactly where things are without digging through logs.

### Why Not Other Approaches

I thought about a single agent with dynamic tool routing. But that gets complex fast—you need to decide which tools to use, in what order, based on context. Hard to observe, hard to debug.

Microservices? Overkill for a local tool. That would add infrastructure headaches I don't need.

Graph-based workflow engine? More flexible, but harder to debug. I went with simple deterministic routing instead.

### What I Learned

Deterministic routing beats dynamic tool selection for production systems. When you can predict what will happen, you can debug it.

Also: observable > invisible. If I have to choose between a system that works silently and one that tells me what it's doing, I'll take the chatty one every time.

---

## 2026-03-19 — Closing the Feedback Loop

### The Problem

I'd run SEO audits, generate recommendations, and then... nothing. Clients would sometimes implement changes, sometimes not. Rankings might improve, might not. I had no idea.

This bothered me. The whole point was to drive results, not just produce reports. But without tracking what happened, I couldn't learn what worked.

### What I Did

Built a change logging system right into the orchestrator. When the agent outputs recommendations, it can include a structured block like `<!-- CHANGE_LOG {...} -->`. The orchestrator parses this and stores it in `memory/seo-changes.json` with a deterministic ID.

Then there's a `seo_impact_review` execution type that reviews all the changes, checks their impact via Google Search Console, and extracts learnings. These learnings feed back into future work—so the agent gets better over time.

### Why JSON, Not a Database?

I could have used a database table, but that requires schema migrations. JSON is simpler and sufficient. Same task + same execution type + same URL = same ID, so writes are idempotent. I use a temp file + atomic replace for safety, so no half-written data if something crashes.

Also deliberately kept change logging at the platform level, not in the agent. Agents shouldn't have to manage their own logging—that couples concerns and makes prompts messier.

### What I Learned

Closing the feedback loop transforms a "reports generator" into a "learning system." 

Also: idempotent operations are non-negotiable in systems that might retry. Write once, write safely.

---

## 2026-03-15 — Skill Packaging with References

### The Problem

Generic instructions like "optimize for search intent" sound good but don't help an agent actually execute. The agent needs to see what "good" looks like—not just rules, but examples.

### What I Did

Packaged skills with structured references:
- `SKILL.md` — what the skill does and when to use it
- `evals/evals.json` — how to evaluate output quality
- `references/` — domain-specific materials (playbooks, examples, templates)

Now "Programmatic SEO" includes real playbooks. "Schema Markup" has actual JSON-LD samples. "Copy Editing" has a plain-English alternatives list. The skill tells you what to do; the references show you how.

### What I Learned

Examples beat instructions. When agents see real patterns, they produce better output.

Also: keeping references separate from core logic means you can improve one without touching the other. Experts can contribute playbooks without knowing how the system works.

---

## 2026-03-09 — Comment Autopilot for Revisions

### The Problem

Users would leave comments like "make this less formal" or "focus on mobile users" on completed tasks. But the agent couldn't see these comments unless users remembered to prefix with `@agent`. People shouldn't have to learn special syntax just to leave feedback.

### What I Did

Two things:

1. **Include all comments in task execution prompts** — not just those with `@agent`. The agent sees everything automatically.

2. **`@agent` is now reserved for revision requests** — when you want the agent to actually redo something, not just add context. This keeps the semantics clear.

For the autopilot loop itself, I implemented a simple polling system:
- Check for `@agent` comments every 5 minutes while the server is running
- Process one at a time, oldest first
- Track state in `comment_actions` table with retry logic
- If it fails, retry once. If it fails again, mark it as exhausted.

There's also a manual endpoint (`POST /automation/comments/process-one`) for when you want to trigger processing immediately.

### Why Polling, Not Webhooks?

Simpler. No external dependencies. The server checks for work when it can; if it's down, comments queue up naturally. This is a local-first tool, not a distributed system—polling fits the use case.

### What I Learned

Single-responsibility for triggers keeps systems predictable. `@agent` means "automate this." Everything else is just context.

---

## 2026-03-08 — Database Environment Handling

### The Problem

The API defaulted to `sqlite:///./kanban.db` at import time. No environment model, no test isolation. Running tests while the server was also running sometimes caused "database locked" errors. Not fun.

### What I Did

Deterministic DB URL resolution:
- `DATABASE_URL` is set → use it
- `APP_ENV=staging` → use `sqlite:///./kanban.staging.db`
- Otherwise → production (`sqlite:///./kanban.db`)

For tests, I force all API database access through an in-memory SQLite engine using `StaticPool`. Tests never touch production files.

### What I Learned

Safe defaults matter. Production should be the default—explicit opt-in for staging. This way, if someone forgets to set an env var, they don't accidentally hit production data.

Test isolation at the infrastructure level is more reliable than hoping developers remember to clean up after themselves.

---

## 2026-02-24 — Starting with File-Based Memory

### The Problem

Every time I ran the agent, it started fresh. No memory of what we'd done before. Every new task required re-explaining the site, keywords, brand voice, competitors. The agent "forgot" everything between runs.

For multi-session SEO work (audit → recommendations → implementation → review), this was a real friction.

### What I Did

File-based memory with three documents:
- `memory/CLAUDE.md` — site overview, keywords, content gaps, constraints
- `memory/seo-strategy.md` — evolving strategy that compounds over time
- `memory/seo-context.md` — current state: what's running, what's done, what's next

At session start, the agent reads CLAUDE.md for context. After executing, it updates the context file. Next session picks up where you left off.

File-based because: no infrastructure needed, human-readable, version-controllable. When something goes wrong, I can read the files and understand what's happening.

### What I Learned

File-based persistence is sufficient for most use cases. Don't add infrastructure unless you need it.

Also: human-readable state enables debugging and manual intervention. I can edit a memory file directly if I need to reset or correct something.

---

## 2026-02-24 — Using the Claude Agent SDK

### The Problem

First version used subprocess calls to the Claude CLI. It worked, but:
- String parsing for output (brittle)
- No typed interfaces
- Error handling was manual

### What I Did

Switched to `claude-agent-sdk>=0.1.44`. Native Python API, typed `AgentConfig`, structured results. OAuth-based auth uses my existing Claude Pro subscription—no API keys to manage.

### What I Learned

First-party SDKs > third-party wrappers. Type safety pays off when debugging. The extra effort to integrate properly is worth it.