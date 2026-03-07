# PLAN.md - SEO Bot Kanban UI

## Problem Statement

Replicate the kanban UI from seo-agent in seo-bot to provide a visual task management interface. The user wants:
- Same styling as seo-agent (Tailwind, DM Sans/Mono fonts)
- FastAPI backend for task CRUD operations
- Integration with existing SEOAgent and Skills
- Red/Green TDD approach

---

## Solution

Create a FastAPI server with task management endpoints and copy the kanban.html UI from seo-agent with modifications to work with seo-bot's API.

---

## Red/Green TDD Approach

### Phase 1: RED (Write Failing Tests First)

#### Test 1: Task API - List Tasks
- [x] **Test**: GET /tasks returns list of tasks
- [x] **Expected**: Returns JSON with tasks array and counts

#### Test 2: Task API - Create Task
- [x] **Test**: POST /tasks with title, description, priority
- [x] **Expected**: New task created with generated ID

#### Test 3: Task API - Update Task
- [x] **Test**: PATCH /tasks/{id} with status change
- [x] **Expected**: Task status updated

#### Test 4: Task API - Delete Task
- [x] **Test**: DELETE /tasks/{id}
- [x] **Expected**: Task deleted successfully

#### Test 5: Task API - Execute Task
- [x] **Test**: POST /tasks/{id}/execute
- [x] **Expected**: Task executed via SEOAgent, result stored

#### Test 6: Kanban HTML - Serve Static File
- [x] **Test**: GET /kanban returns the HTML page
- [x] **Expected**: HTML page loads correctly

---

### Phase 2: GREEN (Implement Solution)

#### Step 1: Create Task Model
- [x] Create `agent/db.py` with SQLite task storage
- [x] Task model: id, title, description, status, priority, assignee, due_date, execution_type, notes, created_at, updated_at

#### Step 2: Create FastAPI Server
- [x] Create `agent/api/main.py` with FastAPI app
- [x] Add CORS middleware
- [x] Create task endpoints

#### Step 3: Create Task Routes
- [x] GET /tasks - list all tasks with filters
- [x] POST /tasks - create new task
- [x] GET /tasks/{id} - get single task
- [x] PATCH /tasks/{id} - update task
- [x] DELETE /tasks/{id} - delete task
- [x] POST /tasks/{id}/execute - execute task via SEOAgent

#### Step 4: Create Kanban HTML
- [x] Copy kanban.html from seo-agent
- [x] Update API_BASE to point to seo-bot's API
- [x] Keep exact same styling
- [x] Run Audit button triggers SEO audit via skills

#### Step 5: Integrate with SEOAgent
- [x] Connect /execute endpoint to existing SEOAgent
- [x] Use existing Skills for task execution

---

### Phase 3: REFACTOR (After Tests Pass)

- [x] Add comments to API endpoints
- [x] Add error handling
- [x] Test the full flow: create task → execute → view result
- [x] Verify kanban UI works end-to-end

---

### Phase 4: Comments Upgrade (NEW)

Added agent comments functionality to track task execution progress:

- [x] Add helper functions for adding comments
  - `add_task_comment()` - generic comment adder
  - `add_task_started_comment()` - task started by agent
  - `add_task_completed_comment()` - task completed with result
  - `add_task_failed_comment()` - task failed with error
  - `add_google_doc_comment()` - Google Doc created (for future use)
  - `add_subtasks_created_comment()` - subtasks created (for future use)

- [x] Modify `/tasks/{id}/execute` endpoint to add comments:
  - Adds "🤖 Task started by agent" when execution begins
  - Adds "✅ Task completed" with result summary on success
  - Adds "❌ Task failed" with error message on failure
  - Increments comment_count on each comment

---

## API Endpoints

```
GET    /tasks              - List all tasks (with status counts)
POST   /tasks              - Create new task
GET    /tasks/{id}         - Get task by ID
PATCH  /tasks/{id}        - Update task
DELETE /tasks/{id}        - Delete task
POST   /tasks/{id}/execute - Execute task via SEOAgent
GET    /tasks/{id}/comments - Get task comments
POST   /tasks/{id}/comments - Add comment to task
POST   /runs/{run_id}/seo-audit - Run SEO audit
GET    /kanban             - Serve kanban UI
```

---

## Task Model Schema

```python
class TaskStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    blocked = "blocked"

class Task:
    id: int
    title: str
    description: Optional[str]
    status: TaskStatus
    priority: int  # 0-3 (0 highest)
    assignee: Optional[str]
    due_date: Optional[str]
    execution_type: Optional[str]  # webflow_publish, blog_write, etc.
    requires_approval: bool
    approved_at: Optional[str]
    notes: Optional[str]
    model: Optional[str]
    parent_task_id: Optional[int]
    comment_count: int
    created_at: str
    updated_at: str
```

---

## Execution Types (from Skills)

| Type | Description |
|------|-------------|
| webflow_publish | Publish to Webflow CMS |
| blog_write | Write blog content |
| internal_links | Add internal links |
| research | Research task |
| seo_audit | Run SEO audit |
| manual | Manual task |

---

## Success Criteria

1. ✅ FastAPI server starts and serves API
2. ✅ Tasks can be created, read, updated, deleted
3. ✅ Tasks can be executed via SEOAgent
4. ✅ Kanban HTML loads with same styling as seo-agent
5. ✅ Run Audit triggers SEO audit skill
6. ✅ All tests pass
7. ✅ Agent adds comments on task execution (started/completed/failed)
