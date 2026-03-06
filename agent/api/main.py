"""
FastAPI server for Kanban UI.

Provides REST API for task management and serves the kanban HTML.
"""

import asyncio
import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# ============================================================================
# EXECUTION TYPE TAXONOMY
# ============================================================================

# Execution types that support autonomous agent execution via the Execute button
EXECUTABLE_TYPES = {
    "research", "rewrite_title", "rewrite_meta_desc", "rewrite_h1",
    "update_schema", "blog_write", "rewrite_blog_content",
    "webflow_publish", "internal_links", "alt_text",
}

# Execution types that require Webflow CMS API access
WEBFLOW_DEPENDENT_TYPES = {
    "rewrite_title", "rewrite_meta_desc", "rewrite_h1",
    "blog_write", "rewrite_blog_content", "webflow_publish", "internal_links",
}


# Database setup
DATABASE_URL = "sqlite:///./kanban.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ========================================================================= MODELS
#===
# DATABASE ============================================================================

class TaskStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    blocked = "blocked"


class TaskModel(Base):
    """Task database model."""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="pending")
    priority = Column(Integer, default=0)
    assignee = Column(String(200), nullable=True)
    due_date = Column(String(20), nullable=True)
    execution_type = Column(String(50), nullable=True)
    requires_approval = Column(Boolean, default=False)
    approved_at = Column(String(20), nullable=True)
    notes = Column(Text, nullable=True)
    model = Column(String(50), nullable=True)
    parent_task_id = Column(Integer, nullable=True)
    comment_count = Column(Integer, default=0)
    created_at = Column(String(20), default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(String(20), default=lambda: datetime.utcnow().isoformat())


class CommentModel(Base):
    """Comment database model."""
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, nullable=False)
    author = Column(String(50), default="user")
    body = Column(Text, nullable=False)
    created_at = Column(String(20), default=lambda: datetime.utcnow().isoformat())


# Create tables
Base.metadata.create_all(bind=engine)


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class TaskCreate(BaseModel):
    """Task creation schema."""
    title: str
    description: Optional[str] = None
    priority: int = 0
    status: str = "pending"
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    execution_type: Optional[str] = None
    requires_approval: bool = False


class TaskUpdate(BaseModel):
    """Task update schema."""
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    execution_type: Optional[str] = None
    requires_approval: Optional[bool] = None
    approved_at: Optional[str] = None
    notes: Optional[str] = None
    model: Optional[str] = None


class TaskResponse(BaseModel):
    """Task response schema."""
    id: int
    title: str
    description: Optional[str]
    status: str
    priority: int
    assignee: Optional[str]
    due_date: Optional[str]
    execution_type: Optional[str]
    requires_approval: bool
    approved_at: Optional[str]
    notes: Optional[str]
    model: Optional[str]
    parent_task_id: Optional[int]
    comment_count: int
    created_at: str
    updated_at: str


class TaskListResponse(BaseModel):
    """Task list response schema."""
    tasks: list
    total: int
    pending_count: int
    in_progress_count: int
    completed_count: int
    blocked_count: int


class CommentCreate(BaseModel):
    """Comment creation schema."""
    author: str = "user"
    body: str


class CommentResponse(BaseModel):
    """Comment response schema."""
    id: int
    task_id: int
    author: str
    body: str
    created_at: str


# ============================================================================
# DATABASE HELPERS
# ============================================================================

def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session():
    """Get a database session (for sync operations)."""
    return SessionLocal()


# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(title="SEO Bot Kanban API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "seo-bot-kanban"}


# ============================================================================
# TASK ENDPOINTS
# ============================================================================

@app.get("/tasks", response_model=TaskListResponse)
def list_tasks(limit: int = 200):
    """List all tasks with counts."""
    db = get_db_session()
    try:
        tasks = db.query(TaskModel).limit(limit).all()
        
        # Convert to response format
        task_list = []
        for task in tasks:
            task_dict = {
                "id": task.id,
                "title": task.title,
                "description": task.description,
                "status": task.status,
                "priority": task.priority,
                "assignee": task.assignee,
                "due_date": task.due_date,
                "execution_type": task.execution_type,
                "requires_approval": task.requires_approval,
                "approved_at": task.approved_at,
                "notes": task.notes,
                "model": task.model,
                "parent_task_id": task.parent_task_id,
                "comment_count": task.comment_count,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
            }
            task_list.append(task_dict)
        
        # Calculate counts
        pending_count = sum(1 for t in tasks if t.status == "pending")
        in_progress_count = sum(1 for t in tasks if t.status == "in_progress")
        completed_count = sum(1 for t in tasks if t.status == "completed")
        blocked_count = sum(1 for t in tasks if t.status == "blocked")
        
        return {
            "tasks": task_list,
            "total": len(tasks),
            "pending_count": pending_count,
            "in_progress_count": in_progress_count,
            "completed_count": completed_count,
            "blocked_count": blocked_count,
        }
    finally:
        db.close()


@app.post("/tasks", response_model=TaskResponse)
def create_task(task: TaskCreate):
    """Create a new task."""
    db = get_db_session()
    try:
        now = datetime.utcnow().isoformat()
        db_task = TaskModel(
            title=task.title,
            description=task.description,
            status=task.status,
            priority=task.priority,
            assignee=task.assignee,
            due_date=task.due_date,
            execution_type=task.execution_type,
            requires_approval=task.requires_approval,
            created_at=now,
            updated_at=now,
        )
        db.add(db_task)
        db.commit()
        db.refresh(db_task)
        
        return {
            "id": db_task.id,
            "title": db_task.title,
            "description": db_task.description,
            "status": db_task.status,
            "priority": db_task.priority,
            "assignee": db_task.assignee,
            "due_date": db_task.due_date,
            "execution_type": db_task.execution_type,
            "requires_approval": db_task.requires_approval,
            "approved_at": db_task.approved_at,
            "notes": db_task.notes,
            "model": db_task.model,
            "parent_task_id": db_task.parent_task_id,
            "comment_count": db_task.comment_count,
            "created_at": db_task.created_at,
            "updated_at": db_task.updated_at,
        }
    finally:
        db.close()


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: int):
    """Get a single task by ID."""
    db = get_db_session()
    try:
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        return {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "priority": task.priority,
            "assignee": task.assignee,
            "due_date": task.due_date,
            "execution_type": task.execution_type,
            "requires_approval": task.requires_approval,
            "approved_at": task.approved_at,
            "notes": task.notes,
            "model": task.model,
            "parent_task_id": task.parent_task_id,
            "comment_count": task.comment_count,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }
    finally:
        db.close()


@app.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, task: TaskUpdate):
    """Update a task."""
    db = get_db_session()
    try:
        db_task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not db_task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        # Update fields
        update_data = task.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_task, key, value)
        
        db_task.updated_at = datetime.utcnow().isoformat()
        db.commit()
        db.refresh(db_task)
        
        return {
            "id": db_task.id,
            "title": db_task.title,
            "description": db_task.description,
            "status": db_task.status,
            "priority": db_task.priority,
            "assignee": db_task.assignee,
            "due_date": db_task.due_date,
            "execution_type": db_task.execution_type,
            "requires_approval": db_task.requires_approval,
            "approved_at": db_task.approved_at,
            "notes": db_task.notes,
            "model": db_task.model,
            "parent_task_id": db_task.parent_task_id,
            "comment_count": db_task.comment_count,
            "created_at": db_task.created_at,
            "updated_at": db_task.updated_at,
        }
    finally:
        db.close()


@app.delete("/tasks/{task_id}")
def delete_task(task_id: int):
    """Delete a task."""
    db = get_db_session()
    try:
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        db.delete(task)
        db.commit()
        
        return {"message": "Task deleted"}
    finally:
        db.close()


def _webflow_available() -> bool:
    """Check if Webflow API credentials are configured."""
    import os
    return bool(os.environ.get("WEBFLOW_ACCESS_TOKEN"))


def _webflow_degradation_note() -> str:
    """Return a note to append when Webflow is not configured."""
    return """
IMPORTANT: Webflow is not configured (WEBFLOW_ACCESS_TOKEN not set).
You cannot make live CMS changes. Instead:
1. Complete all research and content generation steps.
2. Produce the final output (new title, meta description, content, etc.) clearly in your report.
3. Format it so the user can manually paste it into Webflow.
4. Do NOT attempt to call any mcp__webflow__ tools.
"""


def build_execution_prompt(task) -> str:
    """
    Build a workflow-aware prompt for the agent based on the task's execution_type.

    Returns a rich prompt with step-by-step workflow instructions tailored
    to the execution type so the agent can act end-to-end autonomously.

    Args:
        task: TaskModel database object with title, description, execution_type

    Returns:
        Complete prompt string with context and ordered workflow steps
    """
    base = f"Task: {task.title}\n"
    if task.description:
        base += f"Details: {task.description}\n"

    etype = task.execution_type
    webflow_ok = _webflow_available()
    degradation = _webflow_degradation_note() if not webflow_ok else ""

    if etype == "rewrite_title":
        return base + f"""
You are executing an SEO task: research keywords and rewrite the page/post title in Webflow CMS.

WORKFLOW — execute every step in order:

Step 1 — Find the item in Webflow CMS
Use mcp__webflow__list_cms_items (limit=100, offset=0) to list all CMS items.
If there are more than 100 items, paginate with offset=100, offset=200, etc.
Find the item whose "name" field best matches the page referenced in the task title/description.
Use mcp__webflow__get_cms_item to fetch the full item. Note the item_id, current "name", and "seo-title".
If the page is a static Webflow page (homepage, /weweb-agency, /bubble-agency, /faq) — it won't appear
in CMS items. In that case, skip Webflow tool calls and produce copy-paste instructions for
manual update in the Webflow Designer.

Step 2 — Keyword research
Use WebSearch to find SEO keywords for this topic:
- Search: "best keywords for [topic] [current year]"
- Search: "[topic] site keyword competition"
- Review top competitor titles from search results
Identify: primary keyword (highest commercial intent), secondary keywords, competitor title formats.

Step 3 — Generate 3 title options
Rules:
- 50–60 characters including spaces
- Primary keyword near the beginning
- Brand name at the end: "Keyword Phrase | NocodeAssistant"
- Specific to the target audience: SMB founders/COOs/CEOs, $3M-$30M revenue, 5-80 employees
- No filler qualifiers ("Trusted", "Best", "Leading")

Step 4 — Select and update in Webflow
Pick the strongest title. Use mcp__webflow__update_cms_item with:
  item_id: [from Step 1]
  name: [chosen title]
  seo-title: [same title, or a slightly different version if the display name and SEO title should differ]

Step 5 — Publish
Use mcp__webflow__publish_cms_item with the item_id.

Step 6 — Report clearly:
- Old title: [what it was]
- New title: [what you set]
- Keyword rationale: [why this keyword, search intent, competitive context]
- Webflow item ID updated: [id]
{degradation}"""

    elif etype == "rewrite_meta_desc":
        return base + f"""
You are executing an SEO task: research and rewrite the meta description for a page in Webflow CMS.

WORKFLOW — execute every step in order:

Step 1 — Find the item in Webflow CMS
Use mcp__webflow__list_cms_items to find the item matching this page.
Use mcp__webflow__get_cms_item to get the full item. Note the current "seo-desc" value.
If it's a static page, produce copy-paste instructions for manual Webflow Designer update.

Step 2 — Research
Use WebSearch to understand what competitors use in meta descriptions for this topic:
- Search: "[topic] [page type] meta description examples"
- Identify: primary keyword, user intent, strongest value propositions for SMB operators.

Step 3 — Write the meta description
Rules:
- 150–160 characters exactly (count carefully)
- Primary keyword appears naturally in the first half
- Clear value proposition for SMB founders/COOs
- Ends with an implicit or explicit call to action
- No keyword stuffing; reads naturally

Step 4 — Update in Webflow
Use mcp__webflow__update_cms_item:
  item_id: [from Step 1]
  seo-desc: [new description]

Step 5 — Publish
Use mcp__webflow__publish_cms_item.

Step 6 — Report:
- Old description: [what it was]
- New description: [what you set]
- Character count: [exact count]
- Primary keyword used: [keyword]
{degradation}"""

    elif etype == "rewrite_h1":
        return base + f"""
You are executing an SEO task: rewrite the H1 heading for a page and update it in Webflow CMS.

WORKFLOW — execute every step in order:

Step 1 — Fetch the current page
Use WebFetch on the URL referenced in the task to see the current H1.
Also use mcp__webflow__list_cms_items to find the Webflow item.
Use mcp__webflow__get_collection_info to check what fields are available (the H1 may map
to the "name" field or a dedicated headline field).

Step 2 — Research search intent
Use WebSearch: "what do people search for [topic]" and "[topic] user intent"
The H1 must match the expectation a user has after clicking from the SERP.

Step 3 — Write 2 H1 options
Rules:
- Under 70 characters
- Contains the primary keyword
- Specific to this page (not reusable across other pages)
- Direct and clear — no filler, speaks to SMB operators

Step 4 — Update in Webflow
Use mcp__webflow__update_cms_item with the appropriate field (likely "name").

Step 5 — Publish
Use mcp__webflow__publish_cms_item.

Step 6 — Report:
- Old H1: [what it was]
- New H1: [what you set]
- Keyword + intent rationale
{degradation}"""

    elif etype == "blog_write":
        return base + f"""
You are executing an SEO task: research, write, and publish a new blog post to Webflow CMS.

WORKFLOW — execute every step in order:

Step 1 — Keyword research
Use WebSearch to identify:
- The primary keyword and monthly search volume for this topic
- The top 5 ranking pages (their titles, H1s, approximate word counts)
- Secondary keywords and related questions (People Also Ask)
Search: "[topic] keyword research", "[topic] how to", "[topic] guide"

Step 2 — Outline
Create a full post outline:
- SEO title (50-60 chars, keyword-first, ends with "| NocodeAssistant")
- Meta description (150-160 chars)
- H1 (matches or is very close to the SEO title)
- H2 sections with supporting H3s where needed
- Target word count: 800-1500 words for this SMB audience

Step 3 — Write the post
Use the Skill tool to invoke the copywriting skill.
Write the full post following the outline. Must include:
- Primary keyword in first 100 words
- Keyword density ~1-2% (natural usage)
- 2-3 internal links to other nocodeassistant.agency pages
- CTA at the end pointing to the agency's services

Step 4 — Create in Webflow
Use mcp__webflow__create_cms_item with these fields:
  name: [SEO title]
  slug: [kebab-case-url-slug with primary keyword]
  content: [full post content]
  seo-title: [SEO title]
  seo-desc: [meta description]
  excerpt: [2-sentence summary for post cards]
  display-date: [today's date in ISO format]

Step 5 — Publish
Use mcp__webflow__publish_cms_item with the new item's ID.

Step 6 — Report:
- Title: [title]
- URL slug: [slug]
- Word count: [count]
- Primary keyword targeted: [keyword]
- Webflow item ID: [id]
{degradation}"""

    elif etype == "rewrite_blog_content":
        return base + f"""
You are executing an SEO task: rewrite and republish existing blog content for better SEO.

WORKFLOW — execute every step in order:

Step 1 — Fetch the existing post
Use mcp__webflow__list_cms_items to find the post by title match.
Use mcp__webflow__get_cms_item to get the full content.
Note the current title, seo-title, seo-desc, and content.

Step 2 — Audit the current content
Use WebFetch on the live page URL to see how it renders.
Analyze: current keyword targeting, word count, structure, missing sections, outdated info.

Step 3 — Keyword research
Use WebSearch to find what's ranking for this topic now.
Confirm or update the keyword target.

Step 4 — Rewrite
Use the Skill tool: invoke "copy-editing" skill for targeted improvements, or "copywriting"
skill for a full rewrite if the content is poor.
Apply: better keyword targeting, improved structure, updated information, internal links.

Step 5 — Update in Webflow
Use mcp__webflow__update_cms_item with:
  item_id: [from Step 1]
  content: [rewritten content]
  name: [updated title if changed]
  seo-title: [updated SEO title]
  seo-desc: [updated meta description]
  excerpt: [updated excerpt if changed]

Step 6 — Publish
Use mcp__webflow__publish_cms_item.

Step 7 — Report:
- What changed: content, title, meta desc
- Old keyword target vs new keyword target
- Key improvements made
{degradation}"""

    elif etype == "webflow_publish":
        return base + f"""
You are executing an SEO task: publish a Webflow CMS item to the live site.

WORKFLOW — execute every step in order:

Step 1 — Find the item
Use mcp__webflow__list_cms_items to find the item referenced in this task.
If the task description specifies field updates (title, meta desc, etc.), note them.

Step 2 — Update if needed
If the task description specifies field changes, use mcp__webflow__update_cms_item first
with the requested field updates.

Step 3 — Publish
Use mcp__webflow__publish_cms_item with the item's ID.

Step 4 — Confirm and report:
- Item name: [name]
- Item ID: [id]
- Fields updated (if any): [list]
- Published: yes
{degradation}"""

    elif etype == "internal_links":
        return base + f"""
You are executing an SEO task: add internal links between blog posts and pages in Webflow CMS.

Note: Internal links can only be added to CMS rich-text "content" fields via the API.
Static Webflow pages require manual editing in the Designer.

WORKFLOW — execute every step in order:

Step 1 — Get all CMS content
Use mcp__webflow__list_cms_items (paginate with offset if >100 items).
Build a map of each item: title, slug, topic/theme.

Step 2 — Identify link opportunities
For the page(s) mentioned in the task, identify which other site pages are topically related
and would benefit from a link to or from this page.
Prioritize: pages with overlapping topics, service pages, case studies relevant to the post.

Step 3 — Update content with internal links
For each item that needs a link added or received, use mcp__webflow__update_cms_item
to update the "content" field, inserting the anchor text and link naturally in the text.
Format: add the link as an HTML anchor tag within the rich text content.

Step 4 — Publish updated items
Use mcp__webflow__publish_cms_item for each updated item.

Step 5 — Report:
- Items updated: [list with IDs]
- Links added: [source page → target page, anchor text]
- Any static pages that need manual linking (provide copy-paste instructions)
{degradation}"""

    elif etype == "research":
        return base + """
You are executing an SEO research task. This is research-only — no CMS changes.

WORKFLOW — execute every step in order:

Step 1 — Understand the research question
Parse the task title and description to identify what needs researching
(keywords, competitors, content gaps, audience intent, etc.)

Step 2 — Conduct research
Use WebSearch and WebFetch to gather data:
- Keyword research: search volume, difficulty, intent
- Competitor analysis: who ranks, what they cover, their titles and structure
- Industry sources: relevant data points, statistics, trends
Search broadly first, then narrow in on the most relevant findings.

Step 3 — Synthesize findings
Produce a structured report with:
- Primary keyword recommendations (with estimated search volume if findable)
- Competitor analysis (who ranks, why they rank, gaps you can exploit)
- Specific actionable recommendations for nocodeassistant.agency
- Suggested next tasks with their execution types (e.g., rewrite_title, blog_write)

Step 4 — Save findings to task notes.
No CMS changes needed for this task type."""

    elif etype == "alt_text":
        return base + """
You are executing an SEO task: write descriptive alt text for images on a page.

Note: Webflow's CMS API does not expose individual image alt text fields for all image types.
This task will produce copy-paste-ready alt text recommendations for manual implementation.

WORKFLOW — execute every step in order:

Step 1 — Fetch the page
Use WebFetch on the URL referenced in the task.
Find all images with empty alt="" or missing alt attributes.
Categorize them: logos, testimonials/portraits, rating stars, content images, decorative.

Step 2 — Write alt text per category
Rules by image type:
- Client logos: "[Company Name] logo"
- Testimonial portraits: "[Person Name], [Job Title] at [Company Name]"
- G2 / rating stars: "G2 rating 4.8 out of 5 stars" (or aria-hidden if purely decorative)
- Content images: descriptive text of what the image shows and its purpose
- Decorative dividers/backgrounds: leave as alt="" (correct) or add aria-hidden="true"

Step 3 — Produce a report
Format as a table:
| Image Description / URL | Recommended Alt Text |
|---|---|
...

Also provide Webflow-specific instructions for where to add alt text:
- CMS images: in the CMS item's image field settings
- Designer images: select image → click Settings → Alt Text field

Step 4 — Save report to task notes. No automated CMS changes for this task type."""

    elif etype == "update_schema":
        return base + """
You are executing an SEO task: generate JSON-LD structured data for a page.

Note: Webflow's CMS API does not expose custom code injection fields.
This task generates the correct JSON-LD and provides copy-paste instructions for
Webflow's Page Settings > Custom Code > Head Code section.

WORKFLOW — execute every step in order:

Step 1 — Fetch the current page
Use WebFetch on the URL referenced in the task.
Check what JSON-LD schemas already exist (look for <script type="application/ld+json">).
Note the page type: blog post, service page, FAQ, homepage, etc.

Step 2 — Research the correct schema type
Based on the page type, use WebFetch to check the schema.org spec for:
- BlogPosting or Article (blog posts)
- Service (service pages)
- FAQPage (FAQ pages)
- Organization (homepage/about)
- BreadcrumbList (navigation)
Search: "schema.org [schema type] required properties"

Step 3 — Generate the JSON-LD
Write the complete, valid JSON-LD block.
Use https://schema.org (not http://).
Include all recommended fields (not just required).
Validate mentally against the schema.org spec.

Step 4 — Produce implementation instructions
Write step-by-step Webflow instructions:
1. Go to Webflow Designer → select the page → Page Settings (⚙ icon)
2. Scroll to "Custom Code" → "Head Code" section
3. Paste the following block:
[paste the complete JSON-LD <script> block]

Step 5 — Save to task notes. No automated CMS changes."""

    else:
        # Default: flat prompt for unknown or manual types
        prompt = task.title
        if task.description:
            prompt += f"\n\n{task.description}"
        return prompt


@app.post("/tasks/{task_id}/execute", response_model=TaskResponse)
async def execute_task(task_id: int):
    """Execute a task via SEOAgent."""
    db = get_db_session()
    try:
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        # Update status to in_progress
        task.status = "in_progress"
        task.updated_at = datetime.utcnow().isoformat()
        db.commit()
        
        # Execute the task via SEOAgent
        try:
            import os
            from agent.seo_agent import SEOAgent
            from agent.config import AgentConfig

            # Claude Code blocks nested sessions via the CLAUDECODE env var.
            # Unset it so the sub-agent process can start cleanly.
            os.environ.pop("CLAUDECODE", None)

            config = AgentConfig.from_env()
            config.cwd = "/Users/himanshusharma/Code/Codex/seo-bot"
            # Don't load project/user settings — they put the agent into interactive
            # SEO assistant mode. The task prompt is self-contained.
            config.setting_sources = []
            config.system_prompt = (
                "You are an autonomous SEO agent. Execute the given task completely "
                "and autonomously. Use the tools available to you. Report what you did "
                "and the outcome clearly at the end."
            )

            prompt = build_execution_prompt(task)

            result = await SEOAgent.create_and_run(prompt, config)

            # Update task with result
            task.status = "completed"
            task.notes = result
            task.updated_at = datetime.utcnow().isoformat()
            db.commit()
            
        except Exception as e:
            # Mark as blocked on error
            task.status = "blocked"
            task.notes = f"Error: {str(e)}"
            task.updated_at = datetime.utcnow().isoformat()
            db.commit()
        
        return {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "priority": task.priority,
            "assignee": task.assignee,
            "due_date": task.due_date,
            "execution_type": task.execution_type,
            "requires_approval": task.requires_approval,
            "approved_at": task.approved_at,
            "notes": task.notes,
            "model": task.model,
            "parent_task_id": task.parent_task_id,
            "comment_count": task.comment_count,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }
    finally:
        db.close()


# ============================================================================
# COMMENT ENDPOINTS
# ============================================================================

@app.get("/tasks/{task_id}/comments", response_model=list[CommentResponse])
def get_comments(task_id: int):
    """Get all comments for a task."""
    db = get_db_session()
    try:
        comments = db.query(CommentModel).filter(CommentModel.task_id == task_id).all()
        
        return [
            {
                "id": c.id,
                "task_id": c.task_id,
                "author": c.author,
                "body": c.body,
                "created_at": c.created_at,
            }
            for c in comments
        ]
    finally:
        db.close()


@app.post("/tasks/{task_id}/comments", response_model=CommentResponse)
def create_comment(task_id: int, comment: CommentCreate):
    """Add a comment to a task."""
    db = get_db_session()
    try:
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        now = datetime.utcnow().isoformat()
        db_comment = CommentModel(
            task_id=task_id,
            author=comment.author,
            body=comment.body,
            created_at=now,
        )
        db.add(db_comment)
        
        # Increment comment count
        task.comment_count += 1
        
        db.commit()
        db.refresh(db_comment)
        
        return {
            "id": db_comment.id,
            "task_id": db_comment.task_id,
            "author": db_comment.author,
            "body": db_comment.body,
            "created_at": db_comment.created_at,
        }
    finally:
        db.close()


# ============================================================================
# SEO AUDIT ENDPOINT
# ============================================================================

@app.post("/runs/{run_id}/seo-audit")
async def run_seo_audit(run_id: str, days: int = 28, max_rows: int = 1000):
    """Run SEO audit and create tasks."""
    db = get_db_session()
    try:
        # Create SEO audit task
        now = datetime.utcnow().isoformat()
        task = TaskModel(
            title=f"SEO Audit - {run_id}",
            description=f"Run comprehensive SEO audit for the last {days} days",
            status="in_progress",
            priority=0,
            execution_type="seo_audit",
            created_at=now,
            updated_at=now,
        )
        db.add(task)
        db.commit()
        
        # Execute SEO audit
        try:
            import os
            from agent.seo_agent import SEOAgent
            from agent.config import AgentConfig

            os.environ.pop("CLAUDECODE", None)

            config = AgentConfig.from_env()
            config.cwd = "/Users/himanshusharma/Code/Codex/seo-bot"
            config.setting_sources = []
            config.system_prompt = (
                "You are an autonomous SEO agent. Execute the given task completely "
                "and autonomously. Use the tools available to you. Report what you did "
                "and the outcome clearly at the end."
            )

            prompt = f"Run a comprehensive SEO audit analyzing data from the last {days} days. Focus on identifying issues and opportunities."

            result = await SEOAgent.create_and_run(prompt, config)

            # Update task
            task.status = "completed"
            task.notes = result
            task.updated_at = datetime.utcnow().isoformat()
            db.commit()

            # Auto-trigger task breakdown: parse audit findings into Kanban tasks
            breakdown_prompt = f"""The SEO audit has just completed. Here are the findings:

{result}

Now use the Task Breakdown skill to break these findings into actionable tasks.

After creating the task breakdown, create each task in the Kanban board by calling the local API:
- POST http://localhost:8000/tasks
- Body: {{"title": "...", "description": "...", "priority": <0=critical,1=high,2=medium,3=low>, "execution_type": "<see mapping below>"}}

Map priorities as: 🔴 Critical → 0, 🟠 High → 1, 🟡 Medium → 2, 🟢 Low → 3

Map execution_type based on the task category:
- Title tag rewrites (meta title / SEO title) → "rewrite_title"
- Meta description writes or rewrites → "rewrite_meta_desc"
- H1 heading rewrites → "rewrite_h1"
- Alt text for images → "alt_text"
- Schema markup / JSON-LD structured data → "update_schema"
- Writing new blog posts → "blog_write"
- Editing or rewriting existing blog content → "rewrite_blog_content"
- Publishing a CMS item to live → "webflow_publish"
- Adding internal links between pages → "internal_links"
- Keyword research or competitor research → "research"
- Tasks requiring Webflow Designer access (custom code, static page templates, favicon, global settings) → "manual"

Use the Bash tool to make curl requests for each task. Create one Kanban card per actionable task (not subtasks — only parent tasks or standalone tasks).
"""
            try:
                await SEOAgent.create_and_run(breakdown_prompt, config)
            except Exception as e:
                logger.warning(f"Task breakdown failed: {e}")

        except Exception as e:
            task.status = "blocked"
            task.notes = f"Audit error: {str(e)}"
            task.updated_at = datetime.utcnow().isoformat()
            db.commit()

        return {"message": "Audit complete", "tasks": [task.id]}
    finally:
        db.close()


# ============================================================================
# KANBAN HTML
# ============================================================================

@app.get("/kanban", response_class=HTMLResponse)
def get_kanban():
    """Serve the kanban HTML page."""
    kanban_path = Path(__file__).parent.parent.parent / "kanban.html"
    
    if kanban_path.exists():
        return FileResponse(kanban_path)
    
    # If file doesn't exist, return embedded HTML
    return HTMLResponse(content=KANBAN_HTML, media_type="text/html")


# Embedded kanban HTML (fallback if file not found)
KANBAN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SEO Bot — Kanban</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,400&family=DM+Mono:wght@300;400;500&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    fontFamily: {
                        sans: ['DM Sans', 'system-ui', 'sans-serif'],
                        mono: ['DM Mono', 'monospace'],
                    },
                    colors: {
                        blue: {
                            50: '#eff6ff', 100: '#dbeafe', 200: '#bfdbfe',
                            300: '#93c5fd', 400: '#60a5fa', 500: '#3b82f6',
                            600: '#2563eb', 700: '#1d4ed8', 800: '#1e40af', 900: '#1e3a8a',
                        }
                    }
                }
            }
        }
    </script>
    <style>
        /* Base styles from seo-agent */
        *, *::before, *::after { box-sizing: border-box; }
        body {
            font-family: 'DM Sans', system-ui, sans-serif;
            background-color: #f4f6f9;
            color: #111827;
            -webkit-font-smoothing: antialiased;
        }
        #top-accent {
            height: 3px;
            background: linear-gradient(90deg, #2563eb 0%, #3b82f6 50%, #60a5fa 100%);
            position: fixed;
            top: 0; left: 0; right: 0;
            z-index: 60;
        }
        header {
            background: #ffffff;
            border-bottom: 1px solid #e5e7eb;
            position: sticky;
            top: 3px;
            z-index: 40;
            height: 56px;
            display: flex;
            align-items: center;
        }
        .header-inner {
            max-width: 1400px;
            width: 100%;
            margin: 0 auto;
            padding: 0 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .logo-mark {
            width: 32px; height: 32px;
            background: #2563eb;
            border-radius: 8px;
            display: flex; align-items: center; justify-content: center;
            flex-shrink: 0;
        }
        .logo-mark svg { width: 16px; height: 16px; color: white; }
        .app-title { font-size: 15px; font-weight: 600; color: #111827; letter-spacing: -0.01em; }
        .app-subtitle { font-size: 11px; color: #9ca3af; font-weight: 400; letter-spacing: 0.02em; text-transform: uppercase; }
        
        /* Buttons */
        .btn {
            display: inline-flex; align-items: center; gap: 6px;
            padding: 6px 12px;
            border-radius: 7px;
            font-size: 13px;
            font-weight: 500;
            font-family: inherit;
            cursor: pointer;
            border: none;
            transition: all 0.15s ease;
            white-space: nowrap;
        }
        .btn svg { width: 14px; height: 14px; flex-shrink: 0; }
        .btn-ghost { background: transparent; color: #6b7280; }
        .btn-ghost:hover { background: #f4f6f9; color: #374151; }
        .btn-primary { background: #2563eb; color: #ffffff; }
        .btn-primary:hover { background: #1d4ed8; }
        .btn-success { background: #059669; color: #ffffff; }
        .btn-success:hover { background: #047857; }
        
        /* Stats Bar */
        .stats-bar {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            padding: 14px 24px;
            display: flex;
            align-items: center;
            gap: 0;
            margin-bottom: 20px;
        }
        .stat-item { flex: 1; text-align: center; padding: 4px 0; position: relative; }
        .stat-item + .stat-item::before {
            content: '';
            position: absolute;
            left: 0; top: 50%;
            transform: translateY(-50%);
            height: 28px;
            width: 1px;
            background: #e5e7eb;
        }
        .stat-value { font-size: 22px; font-weight: 600; line-height: 1; letter-spacing: -0.02em; margin-bottom: 3px; }
        .stat-label { font-size: 10.5px; color: #9ca3af; font-weight: 500; text-transform: uppercase; letter-spacing: 0.06em; }
        
        /* Kanban */
        .kanban-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
        @media (max-width: 1024px) { .kanban-grid { grid-template-columns: repeat(2, 1fr); } }
        @media (max-width: 640px) { .kanban-grid { grid-template-columns: 1fr; } }
        
        .kanban-col {
            background: #eef0f3;
            border-radius: 12px;
            padding: 12px;
            min-height: 60vh;
            display: flex;
            flex-direction: column;
        }
        .col-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; padding: 2px 0; }
        .col-title { display: flex; align-items: center; gap: 7px; font-size: 12px; font-weight: 600; color: #374151; text-transform: uppercase; letter-spacing: 0.06em; }
        .col-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
        .col-badge { font-size: 10.5px; font-weight: 600; padding: 2px 7px; border-radius: 10px; line-height: 1.4; }
        .col-tasks { display: flex; flex-direction: column; gap: 8px; flex: 1; }
        
        /* Task Card */
        .task-card {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 9px;
            padding: 11px 12px;
            cursor: pointer;
            transition: transform 0.14s ease, box-shadow 0.14s ease, border-color 0.14s ease;
            position: relative;
            overflow: hidden;
        }
        .task-card::before {
            content: '';
            position: absolute;
            left: 0; top: 0; bottom: 0;
            width: 3px;
            border-radius: 9px 0 0 9px;
        }
        .task-card:hover {
            transform: translateY(-1.5px);
            box-shadow: 0 4px 16px rgba(0,0,0,0.07), 0 1px 4px rgba(0,0,0,0.04);
            border-color: #d1d5db;
        }
        
        .card-pending::before { background: #9ca3af; }
        .card-in_progress::before { background: #3b82f6; }
        .card-completed::before { background: #10b981; }
        .card-blocked::before { background: #ef4444; }
        
        .card-title { font-size: 13px; font-weight: 500; color: #111827; line-height: 1.4; margin-bottom: 6px; padding-left: 3px; }
        .card-meta-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 7px; padding-left: 3px; }
        .exec-label { font-size: 11px; color: #9ca3af; display: flex; align-items: center; gap: 4px; }
        .card-meta-right { display: flex; align-items: center; gap: 6px; }
        .card-date { font-size: 11px; color: #9ca3af; }
        
        .pill { display: inline-flex; align-items: center; gap: 3px; padding: 2px 7px; border-radius: 5px; font-size: 11px; font-weight: 500; }
        .pill-priority-0 { background: #fee2e2; color: #b91c1c; }
        .pill-priority-1 { background: #ffedd5; color: #c2410c; }
        .pill-priority-2 { background: #fef3c7; color: #b45309; }
        .pill-priority-3 { background: #dcfce7; color: #15803d; }
        
        /* Modal */
        .modal-backdrop {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(17,24,39,0.55);
            backdrop-filter: blur(2px);
            z-index: 50;
            align-items: flex-start;
            justify-content: center;
            padding: 40px 16px 24px;
            overflow-y: auto;
        }
        .modal-backdrop.open { display: flex; }
        
        .modal-panel {
            background: #ffffff;
            border-radius: 14px;
            width: 100%;
            box-shadow: 0 24px 60px rgba(0,0,0,0.14), 0 2px 8px rgba(0,0,0,0.06);
            max-height: calc(100vh - 64px);
            animation: modal-in 0.18s ease;
        }
        @keyframes modal-in { from { transform: translateY(8px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
        
        .modal-header { padding: 18px 22px 14px; border-bottom: 1px solid #f3f4f6; display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
        .modal-title { font-size: 16px; font-weight: 600; color: #111827; letter-spacing: -0.015em; line-height: 1.35; }
        .modal-close { width: 28px; height: 28px; background: #f4f6f9; border: none; border-radius: 7px; display: flex; align-items: center; justify-content: center; cursor: pointer; color: #6b7280; }
        .modal-close:hover { background: #e5e7eb; color: #374151; }
        
        .field-label { display: block; font-size: 11.5px; font-weight: 500; color: #6b7280; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 5px; }
        .field-input { width: 100%; padding: 8px 11px; font-size: 13.5px; font-family: inherit; color: #111827; background: #f9fafb; border: 1.5px solid #e5e7eb; border-radius: 8px; outline: none; }
        .field-input:focus { border-color: #3b82f6; background: #ffffff; box-shadow: 0 0 0 3px rgba(59,130,246,0.12); }
        textarea.field-input { resize: vertical; min-height: 88px; }
        
        .status-control { display: flex; gap: 0; background: #f4f6f9; border-radius: 8px; padding: 3px; width: fit-content; }
        .status-btn { padding: 5px 12px; font-size: 12px; font-weight: 500; font-family: inherit; border: none; border-radius: 6px; cursor: pointer; background: transparent; color: #6b7280; }
        .status-btn:hover:not(.active) { color: #374151; background: rgba(0,0,0,0.04); }
        .status-btn.active { background: #ffffff; box-shadow: 0 1px 3px rgba(0,0,0,0.1); font-weight: 600; }
        
        .notes-block { background: #0f172a; border-radius: 9px; padding: 14px 16px; font-family: 'DM Mono', monospace; font-size: 12px; line-height: 1.65; color: #94a3b8; max-height: 200px; overflow-y: auto; white-space: pre-wrap; }
        
        .tab-bar { display: flex; border-bottom: 1px solid #f3f4f6; padding: 0 22px; gap: 0; }
        .tab-btn { padding: 10px 0; margin-right: 24px; font-size: 13px; font-weight: 500; background: none; border: none; cursor: pointer; position: relative; }
        .tab-btn.active { color: #2563eb; }
        .tab-btn.active::after { content: ''; position: absolute; bottom: -1px; left: 0; right: 0; height: 2px; background: #2563eb; border-radius: 2px 2px 0 0; }
        
        .modal-body { padding: 18px 22px; overflow-y: auto; flex: 1; }
        .modal-footer { display: flex; align-items: center; justify-content: space-between; padding: 14px 22px; border-top: 1px solid #f3f4f6; }
        .modal-footer-right { display: flex; gap: 8px; }
        
        #toast {
            position: fixed; bottom: 20px; right: 20px;
            background: #111827; color: #f9fafb;
            font-size: 13px; font-family: inherit;
            padding: 10px 16px; border-radius: 9px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.18);
            display: none; z-index: 9999;
            max-width: 320px;
            border-left: 3px solid #3b82f6;
        }
        #toast.toast-error { border-left-color: #ef4444; }
        #toast.toast-success { border-left-color: #10b981; }
    </style>
</head>
<body>
    <div id="top-accent"></div>
    
    <header>
        <div class="header-inner">
            <div style="display:flex;align-items:center;gap:11px;">
                <div class="logo-mark">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
                </div>
                <div>
                    <div class="app-title">SEO Bot</div>
                    <div class="app-subtitle">Kanban Board</div>
                </div>
            </div>
            <div style="display:flex;align-items:center;gap:6px;">
                <button onclick="refreshTasks()" class="btn btn-ghost">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
                    Refresh
                </button>
                <button id="audit-btn" onclick="runAudit()" class="btn btn-success">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/></svg>
                    <span id="audit-btn-label">Run Audit</span>
                </button>
                <button onclick="openCreateModal()" class="btn btn-primary">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
                    Add Task
                </button>
            </div>
        </div>
    </header>

    <main style="max-width:1400px;margin:0 auto;padding:20px 24px 40px;">
        <div class="stats-bar">
            <div class="stat-item"><div class="stat-value" id="total-count" style="color:#111827;">0</div><div class="stat-label">Total</div></div>
            <div class="stat-item"><div class="stat-value" id="pending-count" style="color:#6b7280;">0</div><div class="stat-label">Pending</div></div>
            <div class="stat-item"><div class="stat-value" id="in-progress-count" style="color:#2563eb;">0</div><div class="stat-label">In Progress</div></div>
            <div class="stat-item"><div class="stat-value" id="completed-count" style="color:#059669;">0</div><div class="stat-label">Completed</div></div>
            <div class="stat-item"><div class="stat-value" id="blocked-count" style="color:#dc2626;">0</div><div class="stat-label">Blocked</div></div>
        </div>
        
        <div class="kanban-grid">
            <div class="kanban-col">
                <div class="col-header">
                    <div class="col-title"><div class="col-dot" style="background:#9ca3af;"></div>Pending</div>
                    <span class="col-badge" id="pending-badge" style="background:#e5e7eb;color:#6b7280;">0</span>
                </div>
                <div class="col-tasks" id="pending-tasks"></div>
            </div>
            <div class="kanban-col">
                <div class="col-header">
                    <div class="col-title"><div class="col-dot" style="background:#3b82f6;"></div>In Progress</div>
                    <span class="col-badge" id="in-progress-badge" style="background:#dbeafe;color:#1d4ed8;">0</span>
                </div>
                <div class="col-tasks" id="in-progress-tasks"></div>
            </div>
            <div class="kanban-col">
                <div class="col-header">
                    <div class="col-title"><div class="col-dot" style="background:#10b981;"></div>Completed</div>
                    <span class="col-badge" id="completed-badge" style="background:#d1fae5;color:#047857;">0</span>
                </div>
                <div class="col-tasks" id="completed-tasks"></div>
            </div>
            <div class="kanban-col">
                <div class="col-header">
                    <div class="col-title"><div class="col-dot" style="background:#ef4444;"></div>Blocked</div>
                    <span class="col-badge" id="blocked-badge" style="background:#fee2e2;color:#b91c1c;">0</span>
                </div>
                <div class="col-tasks" id="blocked-tasks"></div>
            </div>
        </div>
    </main>

    <!-- Detail Modal -->
    <div id="detail-modal" class="modal-backdrop" role="dialog" aria-modal="true">
        <div class="modal-panel" style="max-width:640px;">
            <div class="modal-header">
                <div style="flex:1;min-width:0;">
                    <div style="display:flex;align-items:center;gap:6px;margin-bottom:7px;flex-wrap:wrap;">
                        <span id="detail-priority-badge" class="pill"></span>
                    </div>
                    <div class="modal-title" id="detail-title"></div>
                </div>
                <button class="modal-close" onclick="closeDetailModal()">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
                </button>
            </div>
            <div class="tab-bar">
                <button id="tab-details" class="tab-btn active" onclick="switchTab('details')">Details</button>
                <button id="tab-comments" class="tab-btn" onclick="switchTab('comments')">Comments <span id="comment-count-badge" class="tab-count">0</span></button>
            </div>
            <div id="tab-details-panel" class="modal-body">
                <div style="margin-bottom:16px;">
                    <div class="field-label">Status</div>
                    <div class="status-control">
                        <button class="status-btn" id="status-pending" data-status="pending" onclick="setDetailStatus('pending')">Pending</button>
                        <button class="status-btn" id="status-in_progress" data-status="in_progress" onclick="setDetailStatus('in_progress')">In Progress</button>
                        <button class="status-btn" id="status-completed" data-status="completed" onclick="setDetailStatus('completed')">Completed</button>
                        <button class="status-btn" id="status-blocked" data-status="blocked" onclick="setDetailStatus('blocked')">Blocked</button>
                    </div>
                </div>
                <div style="margin-bottom:14px;">
                    <label class="field-label" for="detail-description">Description</label>
                    <textarea id="detail-description" class="field-input" rows="4" placeholder="Add a description…"></textarea>
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
                    <div>
                        <label class="field-label" for="detail-assignee">Assignee</label>
                        <input type="text" id="detail-assignee" class="field-input" placeholder="Assign to…">
                    </div>
                    <div>
                        <label class="field-label" for="detail-due_date">Due Date</label>
                        <input type="date" id="detail-due_date" class="field-input">
                    </div>
                </div>
                <div id="detail-notes-section" style="margin-bottom:14px;display:none;">
                    <label class="field-label">Agent Result</label>
                    <div id="detail-notes" class="notes-block"></div>
                </div>
                <div id="detail-actions" style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:4px;"></div>
            </div>
            <div id="tab-comments-panel" style="display:none;flex-direction:column;flex:1;overflow:hidden;min-height:0;">
                <div id="comments-list" class="modal-body comment-wrap" style="flex:1;overflow-y:auto;max-height:55vh;"></div>
                <div class="comment-input-row" style="display:flex;gap:8px;padding:14px 22px;border-top:1px solid #f3f4f6;">
                    <textarea id="new-comment-body" rows="2" placeholder="Add a comment… (⌘↵ to post)" class="field-input" style="flex:1;"></textarea>
                    <button onclick="postComment()" class="btn btn-primary" style="align-self:flex-end;">Post</button>
                </div>
            </div>
            <div class="modal-footer" id="detail-footer">
                <button onclick="deleteDetailTask()" class="btn btn-danger-ghost" style="background:transparent;color:#dc2626;border:none;font-size:13px;padding:6px 10px;">Delete task</button>
                <div class="modal-footer-right">
                    <button onclick="closeDetailModal()" class="btn btn-ghost">Cancel</button>
                    <button onclick="saveDetailTask()" class="btn btn-primary">Save changes</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Create Modal -->
    <div id="create-modal" class="modal-backdrop" role="dialog" aria-modal="true">
        <div class="modal-panel" style="max-width:480px;">
            <div class="modal-header">
                <div class="modal-title">New Task</div>
                <button class="modal-close" onclick="closeCreateModal()">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
                </button>
            </div>
            <form id="create-form" class="modal-body" style="display:flex;flex-direction:column;gap:14px;">
                <div>
                    <label class="field-label" for="cf-title">Title <span style="color:#ef4444;">*</span></label>
                    <input type="text" id="cf-title" name="title" required class="field-input" placeholder="Task title">
                </div>
                <div>
                    <label class="field-label" for="cf-description">Description</label>
                    <textarea id="cf-description" name="description" rows="3" class="field-input" placeholder="What needs to be done?"></textarea>
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
                    <div>
                        <label class="field-label" for="cf-priority">Priority <span style="color:#9ca3af;">(0 = highest)</span></label>
                        <input type="number" id="cf-priority" name="priority" value="0" min="0" class="field-input">
                    </div>
                    <div>
                        <label class="field-label" for="cf-status">Status</label>
                        <select id="cf-status" name="status" class="field-input">
                            <option value="pending">Pending</option>
                            <option value="in_progress">In Progress</option>
                            <option value="blocked">Blocked</option>
                        </select>
                    </div>
                </div>
                <div>
                    <label class="field-label" for="cf-execution_type">Execution Type</label>
                    <select id="cf-execution_type" name="execution_type" class="field-input">
                        <option value="manual">👤 Manual (no Execute button)</option>
                        <option value="research">🔍 Research</option>
                        <option value="rewrite_title">🏷 Rewrite Title</option>
                        <option value="rewrite_meta_desc">📝 Rewrite Meta Description</option>
                        <option value="rewrite_h1">🔡 Rewrite H1</option>
                        <option value="update_schema">🧩 Update Schema / JSON-LD</option>
                        <option value="blog_write">✍️ Write Blog Post</option>
                        <option value="rewrite_blog_content">✏️ Rewrite Blog Content</option>
                        <option value="webflow_publish">🌐 Publish to Webflow</option>
                        <option value="internal_links">🔗 Add Internal Links</option>
                        <option value="alt_text">🖼 Write Alt Text</option>
                    </select>
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
                    <div>
                        <label class="field-label" for="cf-assignee">Assignee</label>
                        <input type="text" id="cf-assignee" name="assignee" class="field-input" placeholder="Assign to">
                    </div>
                    <div>
                        <label class="field-label" for="cf-due_date">Due Date</label>
                        <input type="date" id="cf-due_date" name="due_date" class="field-input">
                    </div>
                </div>
            </form>
            <div class="modal-footer">
                <div></div>
                <div class="modal-footer-right">
                    <button type="button" onclick="closeCreateModal()" class="btn btn-ghost">Cancel</button>
                    <button type="submit" form="create-form" class="btn btn-primary">Create task</button>
                </div>
            </div>
        </div>
    </div>

    <div id="toast"><span id="toast-message"></span></div>

    <script>
const API_BASE = '';
let currentTasks = [];
let detailTaskId = null;
let activeTab = 'details';

async function fetchTasks() {
    try {
        const r = await fetch(API_BASE + '/tasks?limit=200');
        if (!r.ok) throw new Error('fetch failed');
        const d = await r.json();
        currentTasks = d.tasks;
        updateStats(d);
        renderTasks(d.tasks);
    } catch(e) { showToast('Error: ' + e.message, 'error'); }
}
function refreshTasks() { fetchTasks(); }

function updateStats(d) {
    document.getElementById('total-count').textContent = d.total;
    document.getElementById('pending-count').textContent = d.pending_count;
    document.getElementById('pending-badge').textContent = d.pending_count;
    document.getElementById('in-progress-count').textContent = d.in_progress_count;
    document.getElementById('in-progress-badge').textContent = d.in_progress_count;
    document.getElementById('completed-count').textContent = d.completed_count;
    document.getElementById('completed-badge').textContent = d.completed_count;
    document.getElementById('blocked-count').textContent = d.blocked_count;
    document.getElementById('blocked-badge').textContent = d.blocked_count;
}

const EXEC_LABELS = {
    webflow_publish: '🌐 Publish',
    blog_write: '✍️ Blog Write',
    internal_links: '🔗 Int. Links',
    research: '🔍 Research',
    manual: '👤 Manual',
    seo_audit: '📊 Audit',
    rewrite_title: '🏷 Title',
    rewrite_meta_desc: '📝 Meta Desc',
    rewrite_h1: '🔡 H1',
    update_schema: '🧩 Schema',
    rewrite_blog_content: '✏️ Rewrite',
    alt_text: '🖼 Alt Text',
};
const PRIORITY_PILLS = { 0: 'pill-priority-0', 1: 'pill-priority-1', 2: 'pill-priority-2', 3: 'pill-priority-3' };
const PRIORITY_LABELS = { 0: 'P0 Critical', 1: 'P1 High', 2: 'P2 Medium', 3: 'P3 Low' };

function renderTasks(tasks) {
    const cols = { pending: document.getElementById('pending-tasks'), in_progress: document.getElementById('in-progress-tasks'), completed: document.getElementById('completed-tasks'), blocked: document.getElementById('blocked-tasks') };
    Object.values(cols).forEach(c => c.innerHTML = '');
    tasks.forEach(task => {
        const card = createTaskCard(task);
        const col = cols[task.status];
        if (col) col.appendChild(card);
    });
}

function createTaskCard(task) {
    const card = document.createElement('div');
    card.className = 'task-card card-' + task.status;
    const prioClass = PRIORITY_PILLS[task.priority] || 'pill-priority-0';
    const prioLabel = PRIORITY_LABELS[task.priority] || 'P' + task.priority;
    const execLabel = task.execution_type ? (EXEC_LABELS[task.execution_type] || task.execution_type) : '';
    const commentBadge = task.comment_count > 0 ? '<span class="comment-chip">💬 ' + task.comment_count + '</span>' : '';
    const canExecute = task.execution_type && task.execution_type !== 'manual' && task.execution_type !== 'seo_audit' && task.status !== 'completed' && task.status !== 'in_progress';
    
    card.innerHTML = '<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:6px;"><div class="card-title" style="margin:0;flex:1;">' + escapeHtml(task.title) + '</div><span class="pill ' + prioClass + '" style="flex-shrink:0;margin-top:1px;">' + prioLabel + '</span></div><div class="card-meta-row"><div class="exec-label"><span>' + (execLabel || '—') + '</span></div><div class="card-meta-right">' + commentBadge + (task.due_date ? '<span class="card-date">' + formatDate(task.due_date) + '</span>' : '') + (task.assignee ? '<span class="card-date">' + escapeHtml(task.assignee) + '</span>' : '') + '</div></div><div class="card-actions">' + (canExecute ? '<button onclick="event.stopPropagation();executeTask(' + task.id + ')" class="btn btn-sm" style="background:#4f46e5;color:#fff;">▶ Execute</button>' : '') + '<button onclick="event.stopPropagation();openDetailModal(' + task.id + ')" class="btn btn-sm btn-ghost" style="margin-left:auto;">Open →</button></div>';
    card.addEventListener('click', () => openDetailModal(task.id));
    return card;
}

async function runAudit() {
    const btn = document.getElementById('audit-btn');
    const label = document.getElementById('audit-btn-label');
    btn.disabled = true;
    label.textContent = 'Running…';
    try {
        const r = await fetch(API_BASE + '/runs/audit-' + Date.now() + '/seo-audit', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ days: 28, max_rows: 1000 }) });
        const d = await r.json();
        if (!r.ok) throw new Error(d.detail || r.statusText);
        showToast('Audit complete', 'success');
        fetchTasks();
    } catch(e) { showToast('Error: ' + e.message, 'error'); }
    finally { btn.disabled = false; label.textContent = 'Run Audit'; }
}

async function openDetailModal(taskId) {
    detailTaskId = taskId;
    const task = currentTasks.find(t => t.id === taskId);
    if (!task) return;
    document.getElementById('detail-title').textContent = task.title;
    const prioClass = PRIORITY_PILLS[task.priority] || 'pill-priority-0';
    const prioLabel = PRIORITY_LABELS[task.priority] || 'P' + task.priority;
    const prioBadge = document.getElementById('detail-priority-badge');
    prioBadge.textContent = prioLabel;
    prioBadge.className = 'pill ' + prioClass;
    document.getElementById('detail-description').value = task.description || '';
    document.getElementById('detail-assignee').value = task.assignee || '';
    document.getElementById('detail-due_date').value = task.due_date || '';
    setDetailStatus(task.status);
    if (task.notes) { document.getElementById('detail-notes').textContent = task.notes; document.getElementById('detail-notes-section').style.display = ''; }
    else { document.getElementById('detail-notes-section').style.display = 'none'; }
    const actionsDiv = document.getElementById('detail-actions');
    actionsDiv.innerHTML = '';
    const canExecute = task.execution_type && task.execution_type !== 'manual' && task.execution_type !== 'seo_audit' && task.status !== 'completed' && task.status !== 'in_progress';
    if (canExecute) { const b = document.createElement('button'); b.className = 'btn'; b.style.background = '#4f46e5'; b.style.color = '#fff'; b.textContent = '▶ Execute task'; b.onclick = () => executeTask(task.id); actionsDiv.appendChild(b); }
    if (task.status !== 'completed') { const b = document.createElement('button'); b.className = 'btn btn-success'; b.textContent = '✓ Mark Complete'; b.onclick = () => completeTaskFromDetail(task.id); actionsDiv.appendChild(b); }
    switchTab('details');
    document.getElementById('detail-modal').classList.add('open');
    loadComments(taskId);
}

function closeDetailModal() { document.getElementById('detail-modal').classList.remove('open'); detailTaskId = null; }
function switchTab(tab) {
    activeTab = tab;
    const detPanel = document.getElementById('tab-details-panel');
    const comPanel = document.getElementById('tab-comments-panel');
    const tabDet = document.getElementById('tab-details');
    const tabCom = document.getElementById('tab-comments');
    const footer = document.getElementById('detail-footer');
    if (tab === 'details') { detPanel.style.display = ''; comPanel.style.display = 'none'; tabDet.classList.add('active'); tabCom.classList.remove('active'); footer.style.display = ''; }
    else { detPanel.style.display = 'none'; comPanel.style.display = 'flex'; tabDet.classList.remove('active'); tabCom.classList.add('active'); footer.style.display = 'none'; loadComments(detailTaskId); }
}

async function loadComments(taskId) {
    if (!taskId) return;
    try {
        const r = await fetch(API_BASE + '/tasks/' + taskId + '/comments');
        if (!r.ok) return;
        const comments = await r.json();
        document.getElementById('comment-count-badge').textContent = comments.length;
        const list = document.getElementById('comments-list');
        list.innerHTML = '';
        if (!comments.length) { list.innerHTML = '<p style="font-size:13px;color:#9ca3af;text-align:center;padding:32px 0;">No comments yet.</p>'; return; }
        comments.forEach(c => { const div = document.createElement('div'); div.style.background = c.author === 'agent' ? '#0f172a' : '#eff6ff'; div.style.color = c.author === 'agent' ? '#94a3b8' : '#1e3a8a'; div.style.borderRadius = '10px'; div.style.padding = '11px 14px'; div.innerHTML = '<div style="margin-bottom:5px;"><span style="font-size:11px;font-weight:600;text-transform:uppercase;">' + (c.author === 'agent' ? '🤖 Agent' : '👤 You') + '</span><span style="font-size:10.5px;margin-left:6px;color:' + (c.author === 'agent' ? '#475569' : '#93c5fd') + '">' + formatDateTime(c.created_at) + '</span></div><div style="white-space:pre-wrap;font-size:' + (c.author === 'agent' ? '12.5' : '13.5') + 'px;">' + escapeHtml(c.body) + '</div>'; list.appendChild(div); });
        list.scrollTop = list.scrollHeight;
    } catch(e) { console.error('loadComments error', e); }
}

async function postComment() {
    const body = document.getElementById('new-comment-body').value.trim();
    if (!body || !detailTaskId) return;
    try {
        const r = await fetch(API_BASE + '/tasks/' + detailTaskId + '/comments', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ author: 'user', body }) });
        if (!r.ok) throw new Error('failed');
        document.getElementById('new-comment-body').value = '';
        loadComments(detailTaskId);
        const task = currentTasks.find(t => t.id === detailTaskId);
        if (task) { task.comment_count = (task.comment_count || 0) + 1; renderTasks(currentTasks); }
    } catch(e) { showToast('Error: ' + e.message, 'error'); }
}

async function saveDetailTask() {
    if (!detailTaskId) return;
    const task = currentTasks.find(t => t.id === detailTaskId);
    const activeStatusBtn = document.querySelector('.status-btn.active');
    const activeStatus = activeStatusBtn?.dataset.status || task?.status || 'pending';
    const data = { title: task?.title, description: document.getElementById('detail-description').value || null, assignee: document.getElementById('detail-assignee').value || null, due_date: document.getElementById('detail-due_date').value || null, status: activeStatus };
    try {
        const r = await fetch(API_BASE + '/tasks/' + detailTaskId, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
        if (!r.ok) throw new Error('save failed');
        showToast('Changes saved', 'success');
        closeDetailModal();
        fetchTasks();
    } catch(e) { showToast('Error: ' + e.message, 'error'); }
}

function setDetailStatus(s) { ['pending','in_progress','completed','blocked'].forEach(x => { const btn = document.getElementById('status-' + x); if (x === s) btn.classList.add('active'); else btn.classList.remove('active'); }); }

async function deleteDetailTask() {
    if (!detailTaskId) return;
    if (!confirm('Delete this task?')) return;
    try { const r = await fetch(API_BASE + '/tasks/' + detailTaskId, { method: 'DELETE' }); if (!r.ok) throw new Error('delete failed'); showToast('Task deleted'); closeDetailModal(); fetchTasks(); }
    catch(e) { showToast('Error: ' + e.message, 'error'); }
}

async function completeTaskFromDetail(id) {
    try { const r = await fetch(API_BASE + '/tasks/' + id, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: 'completed' }) }); if (!r.ok) throw new Error('failed'); showToast('Task completed', 'success'); closeDetailModal(); fetchTasks(); }
    catch(e) { showToast('Error: ' + e.message, 'error'); }
}

async function executeTask(id) {
    if (!confirm('Run the agent on this task?')) return;
    showToast('Agent is executing…');
    currentTasks = currentTasks.map(t => t.id === id ? {...t, status:'in_progress'} : t);
    renderTasks(currentTasks);
    if (detailTaskId === id) closeDetailModal();
    try {
        const r = await fetch(API_BASE + '/tasks/' + id + '/execute', { method: 'POST' });
        const d = await r.json();
        if (!r.ok) throw new Error(d.detail || r.statusText);
        showToast('Task executed', 'success');
        fetchTasks();
    } catch(e) { showToast('Error: ' + e.message, 'error'); fetchTasks(); }
}

async function createTask(formData) {
    try { const r = await fetch(API_BASE + '/tasks', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(formData) }); if (!r.ok) throw new Error('failed'); showToast('Task created', 'success'); closeCreateModal(); fetchTasks(); }
    catch(e) { showToast('Error: ' + e.message, 'error'); }
}
function openCreateModal() { document.getElementById('create-form').reset(); document.getElementById('create-modal').classList.add('open'); }
function closeCreateModal() { document.getElementById('create-modal').classList.remove('open'); }

function showToast(msg, type = '') {
    const t = document.getElementById('toast'); const m = document.getElementById('toast-message');
    m.textContent = msg; t.className = '';
    if (type === 'error') t.className = 'toast-error';
    if (type === 'success') t.className = 'toast-success';
    t.style.display = 'block';
    clearTimeout(t._timer);
    t._timer = setTimeout(() => { t.style.display = 'none'; }, 4000);
}

function escapeHtml(text) { const d = document.createElement('div'); d.textContent = text || ''; return d.innerHTML; }
function formatDate(dateStr) { if (!dateStr) return ''; return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }); }
function formatDateTime(isoStr) { if (!isoStr) return ''; const d = new Date(isoStr); return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' · ' + d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }); }

document.getElementById('create-form').addEventListener('submit', function(e) { e.preventDefault(); const data = Object.fromEntries(new FormData(this)); data.priority = parseInt(data.priority) || 0; createTask(data); });
document.addEventListener('keydown', function(e) { if (e.key === 'Escape') { closeDetailModal(); closeCreateModal(); } });
document.getElementById('detail-modal').addEventListener('click', function(e) { if (e.target === this) closeDetailModal(); });
document.getElementById('create-modal').addEventListener('click', function(e) { if (e.target === this) closeCreateModal(); });
document.getElementById('new-comment-body').addEventListener('keydown', function(e) { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') postComment(); });

fetchTasks();
    </script>
</body>
</html>
"""
