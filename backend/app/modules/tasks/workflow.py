"""Task dependencies, templates and the daily workload view.

A task with an unfinished prerequisite is "blocked": it can be planned and edited but
cannot be started or completed. When the last prerequisite is completed the task is
unblocked automatically and an activity entry records it.
"""

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.identity import AuditLog
from app.modules.projects.models import ProjectMilestone
from app.modules.tasks.errors import TaskError
from app.modules.tasks.models import Task, TaskDependency, TaskTemplate, TaskTemplateRun
from app.modules.tasks.schemas import TemplateApply, TemplateInput, TemplateItem, TemplateOut
from app.services.auth import Member

MAX_DEPENDENCIES = 20
WorkflowError = TaskError


def _audit(member: Member, action: str, entity_type: str, entity_id: uuid.UUID, summary: dict[str, object]) -> AuditLog:
    return AuditLog(
        company_id=member.company.id,
        actor_user_id=member.user.id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        summary=summary,
        source="api",
    )


def prerequisites(db: Session, task_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[tuple[uuid.UUID, str, str]]]:
    """For each task: (id, title, status) of the tasks it depends on."""
    if not task_ids:
        return {}
    rows = db.execute(
        select(TaskDependency.task_id, Task.id, Task.title, Task.status)
        .join(Task, Task.id == TaskDependency.depends_on_id)
        .where(TaskDependency.task_id.in_(task_ids), Task.deleted_at.is_(None))
        .order_by(Task.created_at)
    ).all()
    found: dict[uuid.UUID, list[tuple[uuid.UUID, str, str]]] = defaultdict(list)
    for task_id, dep_id, title, status in rows:
        found[task_id].append((dep_id, title, status))
    return found


def open_prerequisites(db: Session, task_id: uuid.UUID) -> list[str]:
    return [title for _, title, status in prerequisites(db, [task_id]).get(task_id, []) if status != "done"]


def ensure_can_progress(db: Session, task: Task, status: str) -> None:
    if status == "todo":
        return
    waiting = open_prerequisites(db, task.id)
    if waiting:
        listed = ", ".join(f"“{title}”" for title in waiting[:3])
        more = f" ve {len(waiting) - 3} görev daha" if len(waiting) > 3 else ""
        raise WorkflowError(409, f"Bu görev bekliyor: önce {listed}{more} tamamlanmalı.")


def release_dependents(db: Session, member: Member, task: Task) -> list[uuid.UUID]:
    """Called after a task is completed; records the dependents that are now free to start."""
    dependents = db.scalars(
        select(Task)
        .join(TaskDependency, TaskDependency.task_id == Task.id)
        .where(TaskDependency.depends_on_id == task.id, Task.deleted_at.is_(None), Task.status != "done")
    ).all()
    released: list[uuid.UUID] = []
    for dependent in dependents:
        remaining = [title for dep_id, title, status in prerequisites(db, [dependent.id]).get(dependent.id, []) if status != "done" and dep_id != task.id]
        if not remaining:
            released.append(dependent.id)
            db.add(_audit(member, "task.unblocked", "task", dependent.id, {"fields": [], "after": task.title}))
    return released


def sync_milestone(db: Session, member: Member, task: Task) -> None:
    """A project stage closes itself when all of its tasks are done and reopens when one is reopened."""
    if task.milestone_id is None:
        return
    milestone = db.scalar(
        select(ProjectMilestone).where(ProjectMilestone.id == task.milestone_id, ProjectMilestone.company_id == member.company.id).with_for_update()
    )
    if milestone is None:
        return
    db.flush()
    statuses = list(db.scalars(select(Task.status).where(Task.milestone_id == milestone.id, Task.deleted_at.is_(None))))
    finished = bool(statuses) and all(status == "done" for status in statuses)
    if finished == (milestone.completed_at is not None):
        return
    now = datetime.now(UTC)
    milestone.completed_at = now if finished else None
    milestone.updated_at = now
    action = "project.milestone_completed" if finished else "project.milestone_reopened"
    db.add(_audit(member, action, "project", milestone.project_id, {"fields": [], "milestone": milestone.title, "auto": True}))


def _would_cycle(db: Session, company_id: uuid.UUID, task_id: uuid.UUID, new_parents: set[uuid.UUID]) -> bool:
    edges: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for child, parent in db.execute(select(TaskDependency.task_id, TaskDependency.depends_on_id).where(TaskDependency.company_id == company_id)).all():
        if child != task_id:
            edges[child].add(parent)
    edges[task_id] = set(new_parents)
    stack, seen = list(new_parents), set()
    while stack:
        current = stack.pop()
        if current == task_id:
            return True
        if current in seen:
            continue
        seen.add(current)
        stack.extend(edges.get(current, ()))
    return False


def set_dependencies(db: Session, member: Member, task: Task, depends_on: list[uuid.UUID]) -> None:
    wanted = set(depends_on)
    if task.id in wanted:
        raise WorkflowError(422, "Bir görev kendisine bağlı olamaz.")
    if len(wanted) > MAX_DEPENDENCIES:
        raise WorkflowError(422, f"Bir görev en çok {MAX_DEPENDENCIES} göreve bağlı olabilir.")
    if wanted:
        valid = set(db.scalars(select(Task.id).where(Task.id.in_(wanted), Task.company_id == member.company.id, Task.deleted_at.is_(None))))
        if valid != wanted:
            raise WorkflowError(422, "Bağlanan görevlerden biri bulunamadı.")
        if _would_cycle(db, member.company.id, task.id, wanted):
            raise WorkflowError(409, "Bu bağlantı döngü oluşturur: görevler birbirini bekleyemez.")
    current = {row.depends_on_id: row for row in db.scalars(select(TaskDependency).where(TaskDependency.task_id == task.id))}
    for parent, row in current.items():
        if parent not in wanted:
            db.delete(row)
    for parent in wanted - current.keys():
        db.add(TaskDependency(company_id=member.company.id, task_id=task.id, depends_on_id=parent))
    if wanted != set(current):
        db.add(_audit(member, "task.dependencies_changed", "task", task.id, {"fields": [], "count": len(wanted)}))


def _template_out(template: TaskTemplate) -> TemplateOut:
    return TemplateOut(
        id=template.id,
        name=template.name,
        description=template.description,
        items=[TemplateItem.model_validate(item) for item in template.items],
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


def list_templates(db: Session, member: Member) -> list[TemplateOut]:
    rows = db.scalars(
        select(TaskTemplate).where(TaskTemplate.company_id == member.company.id, TaskTemplate.deleted_at.is_(None)).order_by(TaskTemplate.name)
    ).all()
    return [_template_out(row) for row in rows]


def _owned_template(db: Session, member: Member, template_id: uuid.UUID) -> TaskTemplate:
    template = db.scalar(
        select(TaskTemplate).where(TaskTemplate.id == template_id, TaskTemplate.company_id == member.company.id, TaskTemplate.deleted_at.is_(None))
    )
    if template is None:
        raise WorkflowError(404, "Şablon bulunamadı.")
    return template


def save_template(db: Session, member: Member, data: TemplateInput, template_id: uuid.UUID | None = None) -> TemplateOut:
    items = [item.model_dump() for item in data.items]
    if template_id is None:
        template = TaskTemplate(company_id=member.company.id, name=data.name, description=data.description, items=items, created_by=member.user.id)
        db.add(template)
        db.flush()
        db.add(_audit(member, "task.template_created", "task_template", template.id, {"name": data.name, "items": len(items)}))
    else:
        template = _owned_template(db, member, template_id)
        template.name, template.description, template.items = data.name, data.description, items
        template.updated_at = datetime.now(UTC)
        db.add(_audit(member, "task.template_updated", "task_template", template.id, {"name": data.name, "items": len(items)}))
    db.commit()
    db.refresh(template)
    return _template_out(template)


def delete_template(db: Session, member: Member, template_id: uuid.UUID) -> None:
    template = _owned_template(db, member, template_id)
    template.deleted_at = datetime.now(UTC)
    db.add(_audit(member, "task.template_deleted", "task_template", template.id, {"name": template.name}))
    db.commit()


def already_applied(db: Session, member: Member, template_id: uuid.UUID, target_key: str) -> bool:
    return (
        db.scalar(
            select(TaskTemplateRun.id).where(
                TaskTemplateRun.company_id == member.company.id, TaskTemplateRun.template_id == template_id, TaskTemplateRun.target_key == target_key
            )
        )
        is not None
    )


def materialize(
    db: Session,
    member: Member,
    template: TaskTemplate,
    *,
    start: date,
    assignee_id: uuid.UUID | None,
    customer_id: uuid.UUID | None,
    order_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
    target_key: str | None,
) -> tuple[TaskTemplateRun, list[Task]]:
    """Create the template's tasks and dependencies in the current transaction (no commit)."""
    duplicate = WorkflowError(409, f"“{template.name}” şablonu bu kayda zaten uygulandı.")
    if target_key is not None and already_applied(db, member, template.id, target_key):
        raise duplicate
    run = TaskTemplateRun(company_id=member.company.id, template_id=template.id, target_key=target_key, task_count=len(template.items), created_by=member.user.id)
    savepoint = db.begin_nested()
    db.add(run)
    try:
        savepoint.commit()
    except IntegrityError:
        savepoint.rollback()
        raise duplicate from None
    created: list[Task] = []
    for raw in template.items:
        item = TemplateItem.model_validate(raw)
        task = Task(
            id=uuid.uuid4(),
            company_id=member.company.id,
            title=item.title,
            description=item.description,
            status="todo",
            priority=item.priority,
            due_date=start + timedelta(days=item.offset_days) if item.offset_days is not None else None,
            assignee_user_id=assignee_id,
            project_id=project_id,
            customer_id=customer_id,
            order_id=order_id,
            created_by=member.user.id,
            template_run_id=run.id,
        )
        db.add(task)
        created.append(task)
    db.flush()
    for index, raw in enumerate(template.items):
        for parent in TemplateItem.model_validate(raw).depends_on:
            db.add(TaskDependency(company_id=member.company.id, task_id=created[index].id, depends_on_id=created[parent].id))
    db.add(_audit(member, "task.template_applied", "task_template", template.id, {"name": template.name, "tasks": len(created), "target": target_key}))
    return run, created


def apply_template(db: Session, member: Member, template_id: uuid.UUID, data: TemplateApply, today: date) -> list[uuid.UUID]:
    template = _owned_template(db, member, template_id)
    target = (
        f"order:{data.order_id}" if data.order_id else f"project:{data.project_id}" if data.project_id else f"customer:{data.customer_id}" if data.customer_id else None
    )
    _, created = materialize(
        db,
        member,
        template,
        start=data.start_date or today,
        assignee_id=data.assignee_id,
        customer_id=data.customer_id,
        order_id=data.order_id,
        project_id=data.project_id,
        target_key=target if data.once_per_record else None,
    )
    db.commit()
    return [task.id for task in created]


def load_counts(db: Session, member: Member, today: date) -> list[dict[str, object]]:
    """Open work per assignee: total, overdue and due within a week."""
    rows = db.execute(
        select(
            Task.assignee_user_id,
            func.count(),
            func.count().filter(Task.due_date < today),
            func.count().filter(Task.due_date.between(today, today + timedelta(days=6))),
        )
        .where(Task.company_id == member.company.id, Task.deleted_at.is_(None), Task.status != "done")
        .group_by(Task.assignee_user_id)
    ).all()
    return [{"assignee_id": assignee, "open": int(total), "overdue": int(late), "this_week": int(week)} for assignee, total, late, week in rows]
