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
- [ ] **Test**: GET /tasks returns list of tasks
- [ ] **Expected**: Returns JSON with tasks array and counts

#### Test 2: Task API - Create Task
- [ ] **Test**: POST /tasks with title, description, priority
- [ ] **Expected**: New task created with generated ID

#### Test 3: Task API - Update Task
- [ ] **Test**: PATCH /tasks/{id} with status change
- [ ] **Expected**: Task status updated

#### Test 4: Task API - Delete Task
- [ ] **Test**: DELETE /tasks/{id}
- [ ] **Expected**: Task deleted successfully

#### Test 5: Task API - Execute Task
- [ ] **Test**: POST /tasks/{id}/execute
- [ ] **Expected**: Task executed via SEOAgent, result stored

#### Test 6: Kanban HTML - Serve Static File
- [ ] **Test**: GET /kanban returns the HTML page
- [ ] **Expected**: HTML page loads correctly

---

### Phase 2: GREEN (Implement Solution)

#### Step 1: Create Task Model
- [ ] Create `agent/db.py` with SQLite task storage
- [ ] Task model: id, title, description, status, priority, assignee, due_date, execution_type, notes, created_at, updated_at

#### Step 2: Create FastAPI Server
- [ ] Create `agent/api/main.py` with FastAPI app
- [ ] Add CORS middleware
- [ ] Create task endpoints

#### Step 3: Create Task Routes
- [ ] GET /tasks - list all tasks with filters
- [ ] POST /tasks - create new task
- [ ] GET /tasks/{id} - get single task
- [ ] PATCH /tasks/{id} - update task
- [ ] DELETE /tasks/{id} - delete task
- [ ] POST /tasks/{id}/execute - execute task via SEOAgent

#### Step 4: Create Kanban HTML
- [ ] Copy kanban.html from seo-agent
- [ ] Update API_BASE to point to seo-bot's API
- [ ] Keep exact same styling
- [ ] Run Audit button triggers SEO audit via skills

#### Step 5: Integrate with SEOAgent
- [ ] Connect /execute endpoint to existing SEOAgent
- [ ] Use existing Skills for task execution

---

### Phase 3: REFACTOR (After Tests Pass)

- [ ] Add comments to API endpoints
- [ ] Add error handling
- [ ] Test the full flow: create task → execute → view result
- [ ] Verify kanban UI works end-to-end

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
