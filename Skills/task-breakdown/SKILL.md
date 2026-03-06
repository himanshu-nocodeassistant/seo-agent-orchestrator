---
description: Break SEO audit findings into actionable tasks with single-output tasks, breakdowns, and subtasks
---

# Task Breakdown Skill

## When to Use

Use this skill after performing any SEO audit, analysis, or research that produces findings or recommendations.

## Core Principle: One Task = One Output

**Every task must achieve exactly ONE specific output.** If a task is complex and would produce multiple outputs, BREAK IT DOWN into smaller tasks.

### Examples:

❌ BAD: "Fix website issues" (too vague, multiple outputs)
✅ GOOD: "Fix missing H1 tag on homepage" (one output)

❌ BAD: "Optimize all pages" (multiple pages = multiple outputs)
✅ GOOD: "Optimize homepage title tag" + "Optimize about page title tag" + ...

## Task Structure

### For Simple Tasks (one output):
- **Task ID**: AUTO-001
- **Priority**: 🔴 High | 🟡 Medium | 🟢 Low
- **Category**: Technical | On-Page | Off-Page | Content
- **Effort**: Small (<1hr) | Medium (1-4hr) | Large (4hr+)
- **Task**: Specific action with ONE clear output
- **Why**: Business impact

### For Complex Tasks (needs subtasks):
Create a PARENT task and break it into CHILD tasks:

**Parent Task**: AUTO-100 - "Improve site speed"
- This is too complex! Break into:

| ID | Priority | Category | Effort | Task | Why | Parent |
|----|----------|----------|--------|------|-----|--------|
| AUTO-101 | 🔴 High | Technical | Medium | Compress images on homepage | Faster load | AUTO-100 |
| AUTO-102 | 🔴 High | Technical | Medium | Enable GZIP compression | Faster load | AUTO-100 |
| AUTO-103 | 🟡 Medium | Technical | Large | Set up CDN | Global speed | AUTO-100 |

## Instructions

### Step 1: Analyze Each Finding
Ask: "What is the ONE specific output of fixing this?"

### Step 2: Break Complex into Subtasks
If a task has multiple steps or affects multiple items, create subtasks:
- Each subtask = one page, one fix, one output
- Link subtasks to parent task

### Step 3: Output Format

**For simple tasks:**
| ID | Priority | Category | Effort | Task | Why |
|----|----------|----------|--------|------|-----|
| AUTO-001 | 🔴 High | Technical | Small | Add H1 tag to homepage | Enables indexing |

**For complex tasks with subtasks:**
| ID | Priority | Category | Effort | Task | Why | Parent |
|----|----------|----------|--------|------|-----|--------|
| AUTO-100 | 🔴 High | Technical | Large | Improve site speed to 90+ | Better UX & SEO | |
| AUTO-101 | 🔴 High | Technical | Medium | Compress images on homepage | Faster load | AUTO-100 |
| AUTO-102 | 🔴 High | Technical | Medium | Enable GZIP compression | Faster load | AUTO-100 |

### Step 4: Save to File
Write to `memory/seo-tasks.md` with:
- Audit date
- Pages/URLs audited
- Task table(s)
- Dependencies noted

## Execution Type Mapping

When creating tasks via the Kanban API, set `execution_type` based on the task category.
This determines which automated workflow runs when someone clicks Execute on the task card.

| Task Category | execution_type |
|---|---|
| Rewrite or optimize a meta title / SEO title | `rewrite_title` |
| Write or rewrite a meta description | `rewrite_meta_desc` |
| Rewrite an H1 heading | `rewrite_h1` |
| Write alt text for images | `alt_text` |
| Add / fix JSON-LD schema markup | `update_schema` |
| Write a new blog post | `blog_write` |
| Edit or rewrite existing blog content | `rewrite_blog_content` |
| Publish a CMS item to the live site | `webflow_publish` |
| Add internal links between pages | `internal_links` |
| Keyword research or competitor research | `research` |
| Tasks needing Webflow Designer (custom code, static pages, templates, favicon) | `manual` |

**Important**: Use `"manual"` only for tasks that genuinely cannot be automated via the
Webflow CMS API — for example, editing static page templates, injecting custom code,
or uploading files. All other tasks should use the specific execution type above so the
Execute button is shown and the agent can act on them autonomously.

## Important

- NEVER create a task that produces multiple outputs
- ALWAYS break complex tasks into single-output subtasks
- Subtasks should be orderable - complete them in priority order
- Update memory/seo-tasks.md after creating tasks
- ALWAYS set the correct `execution_type` when creating Kanban tasks (see table above)
