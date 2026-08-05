"""Comment endpoints.

Extracted from the former agent/api/main.py monolith (see git history).
"""

from fastapi import APIRouter, HTTPException

from agent.api.helpers import add_task_comment, _utcnow_iso
from agent.db import (
    CommentCreate,
    CommentModel,
    CommentResponse,
    TaskModel,
    get_db_session,
)

router = APIRouter()

@router.get("/tasks/{task_id}/comments", response_model=list[CommentResponse])
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


@router.post("/tasks/{task_id}/comments", response_model=CommentResponse)
def create_comment(task_id: int, comment: CommentCreate):
    """Add a comment to a task."""
    db = get_db_session()
    try:
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        now = _utcnow_iso()
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


