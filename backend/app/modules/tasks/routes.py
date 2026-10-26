from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import require_csrf, require_module
from app.core.database import get_db
from app.modules.tasks import workflow
from app.modules.tasks.schemas import (
    Assignee,
    DependencyInput,
    TemplateApplied,
    TemplateApply,
    TemplateInput,
    TemplateOut,
    TodayView,
    TaskDue,
    TaskInput,
    TaskItem,
    TaskPage,
    TaskPriority,
    TaskSort,
    TaskStatus,
    TaskStatusInput,
    TaskSummary,
)
from app.modules.tasks.service import (
    TaskError,
    change_dependencies,
    company_today,
    items_for,
    today_view,
    validate_links,
    create_task,
    delete_task,
    get_task,
    list_assignees,
    list_tasks,
    set_status,
    task_summary,
    update_task,
)
from app.services.auth import Member

router = APIRouter(prefix="/tasks")
tasks_member = require_module("tasks")


def _raise(error: TaskError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.detail)


@router.get("/today", response_model=TodayView)
def read_today(db: Session = Depends(get_db), member: Member = Depends(tasks_member)) -> TodayView:
    return today_view(db, member)


@router.get("/templates", response_model=list[TemplateOut])
def read_templates(db: Session = Depends(get_db), member: Member = Depends(tasks_member)) -> list[TemplateOut]:
    return workflow.list_templates(db, member)


@router.post("/templates", response_model=TemplateOut, status_code=201)
def add_template(payload: TemplateInput, db: Session = Depends(get_db), member: Member = Depends(tasks_member), _: None = Depends(require_csrf)) -> TemplateOut:
    return workflow.save_template(db, member, payload)


@router.put("/templates/{template_id}", response_model=TemplateOut)
def change_template(
    template_id: UUID, payload: TemplateInput, db: Session = Depends(get_db), member: Member = Depends(tasks_member), _: None = Depends(require_csrf)
) -> TemplateOut:
    try:
        return workflow.save_template(db, member, payload, template_id)
    except TaskError as error:
        _raise(error)


@router.delete("/templates/{template_id}", status_code=204)
def remove_template(template_id: UUID, db: Session = Depends(get_db), member: Member = Depends(tasks_member), _: None = Depends(require_csrf)) -> Response:
    try:
        workflow.delete_template(db, member, template_id)
    except TaskError as error:
        _raise(error)
    return Response(status_code=204)


@router.post("/templates/{template_id}/apply", response_model=TemplateApplied, status_code=201)
def apply(
    template_id: UUID, payload: TemplateApply, db: Session = Depends(get_db), member: Member = Depends(tasks_member), _: None = Depends(require_csrf)
) -> TemplateApplied:
    try:
        validate_links(db, member, payload.assignee_id, payload.customer_id, payload.order_id, payload.project_id)
        created = workflow.apply_template(db, member, template_id, payload, company_today(db, member))
    except TaskError as error:
        _raise(error)
    return TemplateApplied(created=items_for(db, member, created))


@router.put("/{task_id}/dependencies", response_model=TaskItem)
def change_task_dependencies(
    task_id: UUID, payload: DependencyInput, db: Session = Depends(get_db), member: Member = Depends(tasks_member), _: None = Depends(require_csrf)
) -> TaskItem:
    try:
        return change_dependencies(db, member, task_id, payload.depends_on)
    except TaskError as error:
        _raise(error)


@router.get("/summary", response_model=TaskSummary)
def read_summary(db: Session = Depends(get_db), member: Member = Depends(tasks_member)) -> TaskSummary:
    return task_summary(db, member)


@router.get("/assignees", response_model=list[Assignee])
def read_assignees(db: Session = Depends(get_db), member: Member = Depends(tasks_member)) -> list[Assignee]:
    return list_assignees(db, member)


@router.get("", response_model=TaskPage)
def read_tasks(
    q: str | None = Query(default=None, max_length=120),
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    assignee: str | None = Query(default=None, max_length=36),
    due: TaskDue | None = None,
    project: str | None = Query(default=None, max_length=36),
    customer: UUID | None = None,
    order: UUID | None = None,
    sort: TaskSort = "due_date",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    member: Member = Depends(tasks_member),
) -> TaskPage:
    try:
        return list_tasks(
            db,
            member,
            query=q,
            status=status,
            priority=priority,
            assignee=assignee,
            due=due,
            project=project,
            customer=customer,
            order=order,
            sort=sort,
            page=page,
            page_size=page_size,
        )
    except TaskError as error:
        _raise(error)


@router.post("", response_model=TaskItem, status_code=201)
def add_task(
    payload: TaskInput,
    db: Session = Depends(get_db),
    member: Member = Depends(tasks_member),
    _: None = Depends(require_csrf),
) -> TaskItem:
    try:
        return create_task(db, member, payload)
    except TaskError as error:
        _raise(error)


@router.get("/{task_id}", response_model=TaskItem)
def read_task(task_id: UUID, db: Session = Depends(get_db), member: Member = Depends(tasks_member)) -> TaskItem:
    try:
        return get_task(db, member, task_id)
    except TaskError as error:
        _raise(error)


@router.put("/{task_id}", response_model=TaskItem)
def change_task(
    task_id: UUID,
    payload: TaskInput,
    db: Session = Depends(get_db),
    member: Member = Depends(tasks_member),
    _: None = Depends(require_csrf),
) -> TaskItem:
    try:
        return update_task(db, member, task_id, payload)
    except TaskError as error:
        _raise(error)


@router.post("/{task_id}/status", response_model=TaskItem)
def move_task(
    task_id: UUID,
    payload: TaskStatusInput,
    db: Session = Depends(get_db),
    member: Member = Depends(tasks_member),
    _: None = Depends(require_csrf),
) -> TaskItem:
    try:
        return set_status(db, member, task_id, payload.status)
    except TaskError as error:
        _raise(error)


@router.delete("/{task_id}", status_code=204)
def remove_task(
    task_id: UUID,
    db: Session = Depends(get_db),
    member: Member = Depends(tasks_member),
    _: None = Depends(require_csrf),
) -> Response:
    try:
        delete_task(db, member, task_id)
    except TaskError as error:
        _raise(error)
    return Response(status_code=204)
