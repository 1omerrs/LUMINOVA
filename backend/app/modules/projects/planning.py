"""Project templates, dependency-based scheduling and the project risk view.

Scheduling is a forward pass over calendar days. A task with a duration starts the day
after its last prerequisite finishes (never before the project start or today, unless it
is already in progress) and finishes `duration_days - 1` days later. Tasks without a
duration keep their own due date and only act as fixed points for their dependents.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.identity import AuditLog, User
from app.modules.projects.models import Project, ProjectMilestone, ProjectTemplate
from app.modules.projects.schemas import (
    MilestoneItem,
    PlanRisk,
    PlanTask,
    ProjectPlan,
    ProjectTemplateInput,
    ProjectTemplateItem,
    ProjectTemplateOut,
    RescheduleResult,
    ScheduleChange,
)
from app.modules.tasks.models import Task, TaskDependency
from app.services.auth import Member

_SEVERITY = {"high": 0, "medium": 1, "low": 2}
# Fixed-date public holidays in Türkiye. Religious holidays move every year and are not included.
FIXED_HOLIDAYS = {(1, 1), (4, 23), (5, 1), (5, 19), (7, 15), (8, 30), (10, 29)}


def is_working_day(day: date) -> bool:
    return day.weekday() < 5 and (day.month, day.day) not in FIXED_HOLIDAYS


def next_working_day(day: date) -> date:
    while not is_working_day(day):
        day += timedelta(days=1)
    return day


def add_working_days(start: date, days: int) -> date:
    """Last day of a task that starts on `start` and lasts `days` working days."""
    day, left = start, days - 1
    while left > 0:
        day += timedelta(days=1)
        if is_working_day(day):
            left -= 1
    return day


class PlanningError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


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


def _stages(items: list[ProjectTemplateItem]) -> list[str]:
    return list(dict.fromkeys(item.stage for item in items))


def _critical_days(items: list[ProjectTemplateItem]) -> int:
    finish: list[int] = []
    for item in items:
        begin = max((finish[parent] for parent in item.depends_on), default=0)
        finish.append(begin + item.duration_days)
    return max(finish, default=0)


def _template_out(template: ProjectTemplate) -> ProjectTemplateOut:
    items = [ProjectTemplateItem.model_validate(item) for item in template.items]
    return ProjectTemplateOut(
        id=template.id,
        name=template.name,
        description=template.description,
        items=items,
        stages=_stages(items),
        total_days=_critical_days(items),
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


def list_templates(db: Session, member: Member) -> list[ProjectTemplateOut]:
    rows = db.scalars(
        select(ProjectTemplate)
        .where(ProjectTemplate.company_id == member.company.id, ProjectTemplate.deleted_at.is_(None))
        .order_by(ProjectTemplate.name)
    ).all()
    return [_template_out(row) for row in rows]


def owned_template(db: Session, member: Member, template_id: uuid.UUID) -> ProjectTemplate:
    template = db.scalar(
        select(ProjectTemplate).where(
            ProjectTemplate.id == template_id, ProjectTemplate.company_id == member.company.id, ProjectTemplate.deleted_at.is_(None)
        )
    )
    if template is None:
        raise PlanningError(404, "Proje şablonu bulunamadı.")
    return template


def save_template(db: Session, member: Member, data: ProjectTemplateInput, template_id: uuid.UUID | None = None) -> ProjectTemplateOut:
    items = [item.model_dump() for item in data.items]
    summary = {"name": data.name, "items": len(items)}
    if template_id is None:
        template = ProjectTemplate(company_id=member.company.id, name=data.name, description=data.description, items=items, created_by=member.user.id)
        db.add(template)
        db.flush()
        db.add(_audit(member, "project.template_created", "project_template", template.id, summary))
    else:
        template = owned_template(db, member, template_id)
        template.name, template.description, template.items = data.name, data.description, items
        template.updated_at = datetime.now(UTC)
        db.add(_audit(member, "project.template_updated", "project_template", template.id, summary))
    db.commit()
    db.refresh(template)
    return _template_out(template)


def delete_template(db: Session, member: Member, template_id: uuid.UUID) -> None:
    template = owned_template(db, member, template_id)
    template.deleted_at = datetime.now(UTC)
    db.add(_audit(member, "project.template_deleted", "project_template", template.id, {"name": template.name}))
    db.commit()


def materialize(db: Session, member: Member, project: Project, template: ProjectTemplate, today: date) -> int:
    """Create the template's stages, tasks and dependencies for a new project (no commit)."""
    items = [ProjectTemplateItem.model_validate(item) for item in template.items]
    milestones: dict[str, ProjectMilestone] = {}
    for position, stage in enumerate(_stages(items)):
        milestone = ProjectMilestone(id=uuid.uuid4(), company_id=member.company.id, project_id=project.id, title=stage, position=position)
        db.add(milestone)
        milestones[stage] = milestone
    db.flush()
    created: list[Task] = []
    for item in items:
        task = Task(
            id=uuid.uuid4(),
            company_id=member.company.id,
            title=item.title,
            description=item.description,
            status="todo",
            priority=item.priority,
            duration_days=item.duration_days,
            project_id=project.id,
            milestone_id=milestones[item.stage].id,
            customer_id=project.customer_id,
            order_id=project.order_id,
            created_by=member.user.id,
        )
        db.add(task)
        created.append(task)
    db.flush()
    for index, item in enumerate(items):
        for parent in item.depends_on:
            db.add(TaskDependency(company_id=member.company.id, task_id=created[index].id, depends_on_id=created[parent].id))
    db.flush()
    schedule = _compute(db, member, project, today)
    _write(db, project, schedule)
    if project.due_date is None:
        project.due_date = schedule.finish
    db.add(_audit(member, "project.template_applied", "project", project.id, {"fields": [], "name": template.name, "tasks": len(created)}))
    return len(created)


@dataclass
class _Schedule:
    tasks: list[Task]
    parents: dict[uuid.UUID, list[uuid.UUID]]
    planned: dict[uuid.UUID, tuple[date, date]]
    finish_of: dict[uuid.UUID, date | None]
    finish: date | None


def _done_on(task: Task) -> date | None:
    return task.completed_at.date() if task.completed_at else task.due_date


def _compute(db: Session, member: Member, project: Project, today: date) -> _Schedule:
    tasks = list(
        db.scalars(
            select(Task)
            .where(Task.company_id == member.company.id, Task.project_id == project.id, Task.deleted_at.is_(None))
            .order_by(Task.start_date.asc().nulls_last(), Task.due_date.asc().nulls_last(), Task.created_at, Task.title, Task.id)
        )
    )
    ids = [task.id for task in tasks]
    parents: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    outside: dict[uuid.UUID, Task] = {}
    if ids:
        for child, parent in db.execute(select(TaskDependency.task_id, TaskDependency.depends_on_id).where(TaskDependency.task_id.in_(ids))).all():
            parents[child].append(parent)
        foreign = {parent for values in parents.values() for parent in values} - set(ids)
        if foreign:
            outside = {task.id: task for task in db.scalars(select(Task).where(Task.id.in_(foreign), Task.deleted_at.is_(None)))}
    by_id = {task.id: task for task in tasks}
    anchor = project.start_date or today
    planned: dict[uuid.UUID, tuple[date, date]] = {}
    finish_of: dict[uuid.UUID, date | None] = {}

    def span(start: date, duration: int) -> date:
        return add_working_days(start, duration) if project.working_days_only else start + timedelta(days=duration - 1)

    def finish(task_id: uuid.UUID, trail: frozenset[uuid.UUID] = frozenset()) -> date | None:
        if task_id in finish_of:
            return finish_of[task_id]
        task = by_id.get(task_id) or outside.get(task_id)
        if task is None or task_id in trail:
            return None
        if task.status == "done" or task.duration_days is None or task_id not in by_id:
            result = _done_on(task) if task.status == "done" else task.due_date
        else:
            earliest = anchor
            for parent in parents.get(task_id, []):
                ends = finish(parent, trail | {task_id})
                if ends is not None:
                    earliest = max(earliest, ends + timedelta(days=1))
            if task.status == "in_progress" and task.start_date is not None:
                start = task.start_date
                due = max(span(start, task.duration_days), today)
            else:
                start = max(earliest, today)
                if project.working_days_only:
                    start = next_working_day(start)
                due = span(start, task.duration_days)
            planned[task_id] = (start, due)
            result = due
        finish_of[task_id] = result
        return result

    for task in tasks:
        finish(task.id)
    ends = [finish_of[task.id] for task in tasks if finish_of.get(task.id) is not None]
    return _Schedule(tasks, parents, planned, finish_of, max(ends) if ends else None)  # type: ignore[type-var]


def _write(db: Session, project: Project, schedule: _Schedule) -> list[ScheduleChange]:
    changes: list[ScheduleChange] = []
    for task in schedule.tasks:
        if task.id not in schedule.planned:
            continue
        start, due = schedule.planned[task.id]
        if (task.start_date, task.due_date) != (start, due):
            changes.append(ScheduleChange(task_id=task.id, title=task.title, old_start=task.start_date, old_due=task.due_date, new_start=start, new_due=due))
            task.start_date, task.due_date = start, due
            task.updated_at = datetime.now(UTC)
    ends: dict[uuid.UUID, date] = {}
    for task in schedule.tasks:
        if task.milestone_id is not None and task.due_date is not None:
            ends[task.milestone_id] = max(ends.get(task.milestone_id, task.due_date), task.due_date)
    if ends:
        for milestone in db.scalars(select(ProjectMilestone).where(ProjectMilestone.id.in_(ends.keys()), ProjectMilestone.completed_at.is_(None))):
            milestone.due_date = ends[milestone.id]
    return changes


def _changes(schedule: _Schedule) -> list[ScheduleChange]:
    found = []
    for task in schedule.tasks:
        if task.id in schedule.planned and (task.start_date, task.due_date) != schedule.planned[task.id]:
            start, due = schedule.planned[task.id]
            found.append(ScheduleChange(task_id=task.id, title=task.title, old_start=task.start_date, old_due=task.due_date, new_start=start, new_due=due))
    return found


def _delay(project: Project, finish: date | None) -> int:
    if finish is None or project.due_date is None:
        return 0
    return max((finish - project.due_date).days, 0)


def reschedule(db: Session, member: Member, project: Project, today: date, *, apply: bool) -> RescheduleResult:
    schedule = _compute(db, member, project, today)
    if not apply:
        return RescheduleResult(changes=_changes(schedule), projected_finish=schedule.finish, delay_days=_delay(project, schedule.finish), applied=False)
    changes = _write(db, project, schedule)
    if changes:
        project.updated_at = datetime.now(UTC)
        db.add(_audit(member, "project.rescheduled", "project", project.id, {"fields": [], "count": len(changes)}))
    db.commit()
    return RescheduleResult(changes=changes, projected_finish=schedule.finish, delay_days=_delay(project, schedule.finish), applied=True)


def _critical(schedule: _Schedule) -> set[uuid.UUID]:
    """Open tasks on the chain that decides the projected finish."""
    if schedule.finish is None:
        return set()
    by_id = {task.id: task for task in schedule.tasks}

    def start_of(task: Task) -> date | None:
        if task.id in schedule.planned:
            return schedule.planned[task.id][0]
        return task.start_date or task.due_date

    critical: set[uuid.UUID] = set()
    stack = [task.id for task in schedule.tasks if task.status != "done" and schedule.finish_of.get(task.id) == schedule.finish]
    while stack:
        current = stack.pop()
        if current in critical:
            continue
        critical.add(current)
        begins = start_of(by_id[current])
        for parent in schedule.parents.get(current, []):
            task = by_id.get(parent)
            ends = schedule.finish_of.get(parent)
            if task is not None and task.status != "done" and begins is not None and ends is not None and ends + timedelta(days=1) >= begins:
                stack.append(parent)
    return critical


def _weight(task: Task) -> int:
    if task.duration_days:
        return task.duration_days
    if task.start_date and task.due_date and task.due_date >= task.start_date:
        return (task.due_date - task.start_date).days + 1
    return 1


def _expected(project: Project, tasks: list[Task], today: date) -> int | None:
    dated = [task for task in tasks if task.due_date is not None]
    if dated:
        total = sum(_weight(task) for task in dated)
        reached = 0.0
        for task in dated:
            span = _weight(task)
            start = task.start_date or (task.due_date - timedelta(days=span - 1))  # type: ignore[operator]
            reached += span * min(max(((today - start).days + 1) / span, 0), 1)
        return round(reached * 100 / total)
    if project.start_date and project.due_date:
        span = (project.due_date - project.start_date).days + 1
        return round(min(max(((today - project.start_date).days + 1) / span, 0), 1) * 100)
    return None


def _day(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def project_plan(db: Session, member: Member, project: Project, today: date, milestones: list[MilestoneItem]) -> ProjectPlan:
    schedule = _compute(db, member, project, today)
    tasks = schedule.tasks
    critical = _critical(schedule)
    status_of = {task.id: task.status for task in tasks}
    outside_open = set()
    foreign = {parent for values in schedule.parents.values() for parent in values} - set(status_of)
    if foreign:
        outside_open = set(db.scalars(select(Task.id).where(Task.id.in_(foreign), Task.status != "done", Task.deleted_at.is_(None))))
    blocked = {
        task.id
        for task in tasks
        if task.status != "done" and any(status_of.get(parent, "done") != "done" or parent in outside_open for parent in schedule.parents.get(task.id, []))
    }
    waiting_on: dict[uuid.UUID, int] = defaultdict(int)
    for child, values in schedule.parents.items():
        if status_of.get(child) not in (None, "done"):
            for parent in values:
                waiting_on[parent] += 1
    assignees = {task.assignee_user_id for task in tasks if task.assignee_user_id}
    names = (
        {user_id: f"{first} {last}" for user_id, first, last in db.execute(select(User.id, User.first_name, User.last_name).where(User.id.in_(assignees))).all()}
        if assignees
        else {}
    )
    plan_tasks = [
        PlanTask(
            id=task.id,
            title=task.title,
            status=task.status,  # type: ignore[arg-type]
            priority=task.priority,  # type: ignore[arg-type]
            start_date=task.start_date,
            due_date=task.due_date,
            duration_days=task.duration_days,
            milestone_id=task.milestone_id,
            depends_on=schedule.parents.get(task.id, []),
            assignee_name=names.get(task.assignee_user_id) if task.assignee_user_id else None,
            blocked=task.id in blocked,
            overdue=task.status != "done" and task.due_date is not None and task.due_date < today,
            critical=task.id in critical,
        )
        for task in tasks
    ]
    total = sum(_weight(task) for task in tasks)
    actual = round(sum(_weight(task) for task in tasks if task.status == "done") * 100 / total) if total else 0
    expected = _expected(project, tasks, today)
    delay = _delay(project, schedule.finish)
    risks: list[PlanRisk] = []
    open_tasks = [task for task in tasks if task.status != "done"]
    if project.status != "completed":
        if delay > 0 and schedule.finish is not None and project.due_date is not None:
            risks.append(
                PlanRisk(
                    kind="late_finish",
                    severity="high",
                    title=f"Plan teslim tarihini {delay} gün aşıyor",
                    detail=f"Bağımlılıklara göre en erken bitiş {_day(schedule.finish)}, hedef {_day(project.due_date)}.",
                )
            )
        if expected is not None and expected - actual >= 15:
            risks.append(
                PlanRisk(
                    kind="behind",
                    severity="high" if expected - actual >= 30 else "medium",
                    title="Plana göre geride",
                    detail=f"Bugüne kadar beklenen ilerleme %{expected}, gerçekleşen %{actual}.",
                )
            )
        for task in sorted((task for task in open_tasks if task.due_date is not None and task.due_date < today), key=lambda task: task.due_date)[:5]:  # type: ignore[arg-type, return-value]
            late = (today - task.due_date).days  # type: ignore[operator]
            risks.append(
                PlanRisk(
                    kind="overdue_task",
                    severity="high" if task.id in critical else "medium",
                    title=f"“{task.title}” {late} gün gecikti",
                    detail="Kritik yolda: proje bitişini doğrudan etkiliyor." if task.id in critical else "Teslim tarihi geçti.",
                    task_id=task.id,
                )
            )
        for task in sorted(open_tasks, key=lambda task: -waiting_on.get(task.id, 0)):
            count = waiting_on.get(task.id, 0)
            if count >= 2 or (count >= 1 and task.due_date is not None and task.due_date < today):
                risks.append(
                    PlanRisk(
                        kind="bottleneck",
                        severity="high" if task.id in critical else "medium",
                        title=f"Darboğaz: “{task.title}”",
                        detail=f"{count} görev bunun bitmesini bekliyor.",
                        task_id=task.id,
                    )
                )
        soon = [task for task in open_tasks if task.assignee_user_id is None and (task.id in critical or (task.due_date is not None and task.due_date <= today + timedelta(days=7)))]
        if soon:
            risks.append(
                PlanRisk(
                    kind="unassigned",
                    severity="medium",
                    title=f"{len(soon)} görevin sorumlusu yok",
                    detail="Yakında başlayacak veya kritik yoldaki görevler: " + ", ".join(f"“{task.title}”" for task in soon[:3]) + ("…" if len(soon) > 3 else ""),
                    task_id=soon[0].id,
                )
            )
        for milestone in milestones:
            if milestone.overdue:
                risks.append(PlanRisk(kind="late_milestone", severity="medium", title=f"“{milestone.title}” aşaması gecikti", detail=f"Hedef tarih {_day(milestone.due_date)} idi."))  # type: ignore[arg-type]
        if open_tasks and all(task.due_date is None for task in open_tasks):
            risks.append(PlanRisk(kind="no_plan", severity="low", title="Görevlerde tarih yok", detail="Tarih ve süre girilmeden gecikme ve darboğaz hesaplanamaz."))
    risks.sort(key=lambda risk: _SEVERITY[risk.severity])
    return ProjectPlan(
        today=today,
        tasks=plan_tasks,
        milestones=milestones,
        actual_progress=actual,
        expected_progress=expected,
        projected_finish=schedule.finish,
        delay_days=delay,
        risks=risks,
        pending_changes=len(_changes(schedule)),
    )
