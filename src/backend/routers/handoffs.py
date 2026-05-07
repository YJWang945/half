from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from access import get_owned_project
from auth import get_current_user
from database import get_db
from models import Project, Task, TaskHandoff, User
from schemas import UtcDatetimeModel
from services.handoffs import (
    HANDOFF_TEMPLATES,
    build_handoff_document,
    generate_handoff_from_template,
    handoff_has_content,
    parse_handoff_document,
    serialize_handoff_document,
)

router = APIRouter(tags=["handoffs"])


class TaskHandoffResponse(UtcDatetimeModel):
    id: int
    project_id: int
    from_task_id: str
    from_task_name: str
    to_task_id: str
    to_task_name: str
    summary: str
    details: str
    has_content: bool
    created_at: datetime | None
    updated_at: datetime | None


class TaskHandoffUpdateRequest(BaseModel):
    summary: str = ""
    details: str = ""


class HandoffTemplateItem(BaseModel):
    key: str
    label: str


def _build_handoff_response(handoff: TaskHandoff, from_task: Task, to_task: Task) -> TaskHandoffResponse:
    document = parse_handoff_document(handoff.handoff_json, from_task, to_task)
    return TaskHandoffResponse(
        id=handoff.id,
        project_id=handoff.project_id,
        from_task_id=from_task.task_code,
        from_task_name=from_task.task_name,
        to_task_id=to_task.task_code,
        to_task_name=to_task.task_name,
        summary=str(document.get("summary", "")),
        details=str(document.get("details", "")),
        has_content=handoff_has_content(document),
        created_at=handoff.created_at,
        updated_at=handoff.updated_at,
    )


def _get_owned_handoff(db: Session, handoff_id: int, user: User) -> tuple[TaskHandoff, Task, Task]:
    handoff = db.query(TaskHandoff).filter(TaskHandoff.id == handoff_id).first()
    if handoff is None:
        raise HTTPException(status_code=404, detail="Handoff not found")

    from_task = db.query(Task).filter(Task.id == handoff.from_task_id).first()
    to_task = db.query(Task).filter(Task.id == handoff.to_task_id).first()
    if from_task is None or to_task is None or from_task.project_id != to_task.project_id:
        raise HTTPException(status_code=404, detail="Handoff tasks not found")

    project = db.query(Project).filter(Project.id == handoff.project_id).first()
    if project is None or project.created_by != user.id:
        raise HTTPException(status_code=404, detail="Handoff not found")
    if from_task.project_id != handoff.project_id or to_task.project_id != handoff.project_id:
        raise HTTPException(status_code=400, detail="Handoff edge is inconsistent with project")
    return handoff, from_task, to_task


@router.get("/api/projects/{project_id}/handoffs", response_model=list[TaskHandoffResponse])
def list_project_handoffs(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = get_owned_project(db, project_id, user)
    tasks = db.query(Task).filter(Task.project_id == project.id).all()
    task_by_id = {task.id: task for task in tasks}
    handoffs = db.query(TaskHandoff).filter(TaskHandoff.project_id == project.id).order_by(TaskHandoff.id.asc()).all()

    responses: list[TaskHandoffResponse] = []
    for handoff in handoffs:
        from_task = task_by_id.get(handoff.from_task_id)
        to_task = task_by_id.get(handoff.to_task_id)
        if from_task is None or to_task is None:
            continue
        responses.append(_build_handoff_response(handoff, from_task, to_task))
    return responses


@router.put("/api/handoffs/{handoff_id}", response_model=TaskHandoffResponse)
def update_handoff(
    handoff_id: int,
    body: TaskHandoffUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    handoff, from_task, to_task = _get_owned_handoff(db, handoff_id, user)
    document = build_handoff_document(
        from_task.task_code,
        to_task.task_code,
        summary=body.summary,
        details=body.details,
    )
    handoff.handoff_json = serialize_handoff_document(document)
    db.commit()
    db.refresh(handoff)
    return _build_handoff_response(handoff, from_task, to_task)


@router.get("/api/handoffs/templates", response_model=list[HandoffTemplateItem])
def list_handoff_templates():
    """返回可用的 handoff 模板预设列表"""
    return [
        HandoffTemplateItem(key=key, label=info["label"])
        for key, info in HANDOFF_TEMPLATES.items()
    ]


@router.post("/api/handoffs/{handoff_id}/generate-from-template", response_model=TaskHandoffResponse)
def generate_handoff_from_template_endpoint(
    handoff_id: int,
    template_key: str = "general",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """使用预设模板生成 handoff 草稿并保存"""
    handoff, from_task, to_task = _get_owned_handoff(db, handoff_id, user)
    if template_key not in HANDOFF_TEMPLATES:
        raise HTTPException(status_code=400, detail=f"Unknown template: {template_key}")

    document = generate_handoff_from_template(
        from_task.task_code,
        to_task.task_code,
        template_key,
    )
    handoff.handoff_json = serialize_handoff_document(document)
    db.commit()
    db.refresh(handoff)
    return _build_handoff_response(handoff, from_task, to_task)
