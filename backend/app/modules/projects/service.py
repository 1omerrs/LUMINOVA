import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, literal, or_, select, update
from sqlalchemy.orm import Session

from app.models.identity import AuditLog
from app.modules.customers.models import Customer
from app.modules.projects import planning
from app.modules.projects.models import Project, ProjectMilestone
from app.modules.quotes.models import Quote
from app.modules.sales.models import SalesOrder
from app.modules.projects.schemas import (
    MilestoneInput,
    MilestoneItem,
    ProjectInput,
    ProjectItem,
    ProjectPage,
    ProjectPlan,
    ProjectSort,
    ProjectStatus,
    ProjectSummary,
    RescheduleResult,
)
from app.modules.tasks.models import Task
from app.modules.tasks.service import company_today
from app.services.auth import Member

_TURKISH = "tr-TR-x-icu"
MILESTONE_LIMIT = 30
_ORDER = {
    "due_date": (Project.due_date.asc().nulls_last(), Project.created_at.desc(), Project.id.asc()),
    "-created_at": (Project.created_at.desc(), Project.id.desc()),
    "name": (Project.name.collate(_TURKISH).asc(), Project.id.asc()),
}


ProjectError = planning.PlanningError


def _task_counts(member: Member, today: date):
    open_task = Task.status != "done"
    return (
        select(
            Task.project_id.label("project_id"),
            func.count().label("total"),
            func.count().filter(Task.status == "done").label("done"),
            func.count().filter(open_task, Task.due_date < today).label("overdue"),
        )
        .where(Task.company_id == member.company.id, Task.deleted_at.is_(None), Task.project_id.is_not(None))
        .group_by(Task.project_id)
        .subquery()
    )


def list_projects(
    db: Session,
    member: Member,
    *,
    query: str | None,
    status: ProjectStatus | None,
    sort: ProjectSort,
    page: int,
    page_size: int,
) -> ProjectPage:
    today = company_today(db, member)
    filters = [Project.company_id == member.company.id, Project.deleted_at.is_(None)]
    if status is not None:
        filters.append(Project.status == status)
    term = (query or "").strip()
    if term:
        pattern = func.lower(literal(f"%{term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')}%").collate(_TURKISH))
        filters.append(
            or_(
                func.lower(Project.name.collate(_TURKISH)).like(pattern, escape="\\"),
                func.lower(Customer.name.collate(_TURKISH)).like(pattern, escape="\\"),
            )
        )
    counts = _task_counts(member, today)
    base = (
        select(Project, Customer.name, counts.c.total, counts.c.done, counts.c.overdue)
        .outerjoin(Customer, Customer.id == Project.customer_id)
        .outerjoin(counts, counts.c.project_id == Project.id)
        .where(*filters)
    )
    total = db.scalar(select(func.count()).select_from(Project).outerjoin(Customer, Customer.id == Project.customer_id).where(*filters)) or 0
    rows = db.execute(base.order_by(*_ORDER[sort]).offset((page - 1) * page_size).limit(page_size)).all()
    stats = _milestone_stats(db, member, [row[0].id for row in rows])
    codes = _codes(db, [row[0] for row in rows])
    return ProjectPage(
        items=[_item(project, customer, all_, done, late, today, stats.get(project.id), codes) for project, customer, all_, done, late in rows],
        total=int(total),
        page=page,
        page_size=page_size,
        today=today,
    )


def project_summary(db: Session, member: Member) -> ProjectSummary:
    today = company_today(db, member)
    scope = (Project.company_id == member.company.id, Project.deleted_at.is_(None))
    counts = {status: int(count) for status, count in db.execute(select(Project.status, func.count()).where(*scope).group_by(Project.status)).all()}
    overdue = db.scalar(select(func.count()).select_from(Project).where(*scope, Project.status != "completed", Project.due_date < today)) or 0
    return ProjectSummary(
        planned=counts.get("planned", 0),
        active=counts.get("active", 0),
        on_hold=counts.get("on_hold", 0),
        completed=counts.get("completed", 0),
        overdue=int(overdue),
    )


def get_project(db: Session, member: Member, project_id: uuid.UUID) -> ProjectItem:
    return _read(db, member, _owned(db, member, project_id))


def get_plan(db: Session, member: Member, project_id: uuid.UUID) -> ProjectPlan:
    project = _owned(db, member, project_id)
    return planning.project_plan(db, member, project, company_today(db, member), list_milestones(db, member, project.id))


def reschedule_project(db: Session, member: Member, project_id: uuid.UUID, *, apply: bool) -> RescheduleResult:
    project = _owned(db, member, project_id, lock=apply)
    return planning.reschedule(db, member, project, company_today(db, member), apply=apply)


def create_project(db: Session, member: Member, data: ProjectInput) -> ProjectItem:
    customer_id = _resolve_links(db, member, data)
    template = planning.owned_template(db, member, data.template_id) if data.template_id else None
    project = Project(
        id=uuid.uuid4(),
        company_id=member.company.id,
        name=data.name,
        description=data.description,
        status=data.status,
        customer_id=customer_id,
        quote_id=data.quote_id,
        order_id=data.order_id,
        template_id=template.id if template else None,
        working_days_only=data.working_days_only,
        start_date=data.start_date,
        due_date=data.due_date,
        completed_at=datetime.now(UTC) if data.status == "completed" else None,
        created_by=member.user.id,
    )
    db.add(project)
    db.add(_audit(member, "project.created", project, sorted(data.model_dump(exclude_none=True))))
    if template is not None:
        db.flush()
        planning.materialize(db, member, project, template, company_today(db, member))
    db.commit()
    return _read(db, member, project)


def update_project(db: Session, member: Member, project_id: uuid.UUID, data: ProjectInput) -> ProjectItem:
    project = _owned(db, member, project_id, lock=True)
    kept = {field: getattr(project, field) for field in ("quote_id", "order_id", "working_days_only") if field not in data.model_fields_set}
    data = data.model_copy(update=kept)
    if (data.customer_id, data.quote_id, data.order_id) != (project.customer_id, project.quote_id, project.order_id):
        data = data.model_copy(update={"customer_id": _resolve_links(db, member, data)})
    values = data.model_dump(exclude={"template_id"})
    changed = [field for field, value in values.items() if getattr(project, field) != value]
    if not changed:
        return _read(db, member, project)
    for field in changed:
        setattr(project, field, values[field])
    if "status" in changed:
        project.completed_at = datetime.now(UTC) if data.status == "completed" else None
    project.updated_at = datetime.now(UTC)
    db.add(_audit(member, "project.updated", project, changed))
    db.commit()
    return _read(db, member, project)


def delete_project(db: Session, member: Member, project_id: uuid.UUID) -> None:
    project = _owned(db, member, project_id, lock=True)
    now = datetime.now(UTC)
    unlinked = db.execute(
        update(Task).where(Task.company_id == member.company.id, Task.project_id == project.id).values(project_id=None, milestone_id=None, updated_at=now)
    ).rowcount
    project.deleted_at = now
    project.updated_at = now
    db.add(_audit(member, "project.deleted", project, [], {"unlinked_tasks": int(unlinked or 0)}))
    db.commit()


def _resolve_links(db: Session, member: Member, data: ProjectInput) -> uuid.UUID | None:
    """Validate customer, quote and order; a project linked to a quote or order inherits its customer."""
    customer_id = data.customer_id
    for model, value, label in ((Quote, data.quote_id, "teklif"), (SalesOrder, data.order_id, "sipariş")):
        if value is None:
            continue
        owner = db.scalar(select(model.customer_id).where(model.id == value, model.company_id == member.company.id))
        if owner is None:
            raise ProjectError(422, f"Seçilen {label} bulunamadı.")
        if customer_id is None:
            customer_id = owner
        elif owner != customer_id:
            raise ProjectError(422, f"Seçilen {label} başka bir müşteriye ait.")
    if customer_id is not None:
        exists = db.scalar(
            select(Customer.id).where(Customer.id == customer_id, Customer.company_id == member.company.id, Customer.deleted_at.is_(None))
        )
        if exists is None:
            raise ProjectError(422, "Seçilen müşteri bulunamadı.")
    return customer_id


def _owned(db: Session, member: Member, project_id: uuid.UUID, *, lock: bool = False) -> Project:
    statement = select(Project).where(Project.id == project_id, Project.company_id == member.company.id, Project.deleted_at.is_(None))
    if lock:
        statement = statement.with_for_update()
    project = db.scalar(statement)
    if project is None:
        raise ProjectError(404, "Proje bulunamadı.")
    return project


def _audit(member: Member, action: str, project: Project, fields: list[str], extra: dict[str, object] | None = None) -> AuditLog:
    return AuditLog(
        company_id=member.company.id,
        actor_user_id=member.user.id,
        action=action,
        entity_type="project",
        entity_id=str(project.id),
        summary={"fields": fields, **(extra or {})},
        source="api",
    )


def _read(db: Session, member: Member, project: Project) -> ProjectItem:
    db.refresh(project)
    today = company_today(db, member)
    counts = _task_counts(member, today)
    row = db.execute(
        select(Customer.name, counts.c.total, counts.c.done, counts.c.overdue)
        .select_from(Project)
        .outerjoin(Customer, Customer.id == Project.customer_id)
        .outerjoin(counts, counts.c.project_id == Project.id)
        .where(Project.id == project.id)
    ).one()
    return _item(project, row[0], row[1], row[2], row[3], today, _milestone_stats(db, member, [project.id]).get(project.id), _codes(db, [project]))


def _codes(db: Session, projects: list[Project]) -> dict[uuid.UUID, str]:
    quotes = {project.quote_id for project in projects if project.quote_id}
    orders = {project.order_id for project in projects if project.order_id}
    codes: dict[uuid.UUID, str] = {}
    if quotes:
        codes.update({quote_id: f"TK-{number:04d}" for quote_id, number in db.execute(select(Quote.id, Quote.number).where(Quote.id.in_(quotes))).all()})
    if orders:
        codes.update({order_id: f"SP-{number:04d}" for order_id, number in db.execute(select(SalesOrder.id, SalesOrder.number).where(SalesOrder.id.in_(orders))).all()})
    return codes


MilestoneStats = tuple[int, int, str | None, date | None]


def _milestone_stats(db: Session, member: Member, project_ids: list[uuid.UUID]) -> dict[uuid.UUID, MilestoneStats]:
    if not project_ids:
        return {}
    rows = db.scalars(
        select(ProjectMilestone)
        .where(ProjectMilestone.company_id == member.company.id, ProjectMilestone.project_id.in_(project_ids))
        .order_by(ProjectMilestone.project_id, ProjectMilestone.position)
    ).all()
    stats: dict[uuid.UUID, MilestoneStats] = {}
    for milestone in rows:
        total, done, title, due = stats.get(milestone.project_id, (0, 0, None, None))
        if milestone.completed_at is not None:
            done += 1
        elif title is None:
            title, due = milestone.title, milestone.due_date
        stats[milestone.project_id] = (total + 1, done, title, due)
    return stats


def list_milestones(db: Session, member: Member, project_id: uuid.UUID) -> list[MilestoneItem]:
    project = _owned(db, member, project_id)
    today = company_today(db, member)
    rows = db.scalars(select(ProjectMilestone).where(ProjectMilestone.project_id == project.id).order_by(ProjectMilestone.position)).all()
    return [_milestone(row, today) for row in rows]


def add_milestone(db: Session, member: Member, project_id: uuid.UUID, data: MilestoneInput) -> list[MilestoneItem]:
    project = _owned(db, member, project_id, lock=True)
    count = db.scalar(select(func.count()).select_from(ProjectMilestone).where(ProjectMilestone.project_id == project.id)) or 0
    if count >= MILESTONE_LIMIT:
        raise ProjectError(409, f"Bir projede en çok {MILESTONE_LIMIT} aşama olabilir.")
    last = db.scalar(select(func.max(ProjectMilestone.position)).where(ProjectMilestone.project_id == project.id))
    now = datetime.now(UTC)
    db.add(
        ProjectMilestone(
            company_id=member.company.id,
            project_id=project.id,
            title=data.title,
            due_date=data.due_date,
            position=int(last if last is not None else -1) + 1,
            completed_at=now if data.done else None,
        )
    )
    project.updated_at = now
    db.add(_audit(member, "project.milestone_added", project, [], {"milestone": data.title}))
    db.commit()
    return list_milestones(db, member, project.id)


def update_milestone(db: Session, member: Member, project_id: uuid.UUID, milestone_id: uuid.UUID, data: MilestoneInput) -> list[MilestoneItem]:
    project, milestone = _owned_milestone(db, member, project_id, milestone_id)
    now = datetime.now(UTC)
    was_done = milestone.completed_at is not None
    changed = milestone.title != data.title or milestone.due_date != data.due_date
    milestone.title = data.title
    milestone.due_date = data.due_date
    if data.done != was_done:
        milestone.completed_at = now if data.done else None
        db.add(_audit(member, "project.milestone_completed" if data.done else "project.milestone_reopened", project, [], {"milestone": data.title}))
    elif changed:
        db.add(_audit(member, "project.milestone_updated", project, [], {"milestone": data.title}))
    if changed or data.done != was_done:
        milestone.updated_at = now
        project.updated_at = now
        db.commit()
    return list_milestones(db, member, project.id)


def move_milestone(db: Session, member: Member, project_id: uuid.UUID, milestone_id: uuid.UUID, direction: str) -> list[MilestoneItem]:
    project, milestone = _owned_milestone(db, member, project_id, milestone_id)
    rows = list(db.scalars(select(ProjectMilestone).where(ProjectMilestone.project_id == project.id).order_by(ProjectMilestone.position).with_for_update()))
    index = next(i for i, row in enumerate(rows) if row.id == milestone.id)
    target = index - 1 if direction == "up" else index + 1
    if 0 <= target < len(rows):
        rows[index], rows[target] = rows[target], rows[index]
        for position, row in enumerate(rows):
            row.position = position
        db.commit()
    return list_milestones(db, member, project.id)


def delete_milestone(db: Session, member: Member, project_id: uuid.UUID, milestone_id: uuid.UUID) -> list[MilestoneItem]:
    project, milestone = _owned_milestone(db, member, project_id, milestone_id)
    db.add(_audit(member, "project.milestone_removed", project, [], {"milestone": milestone.title}))
    db.delete(milestone)
    project.updated_at = datetime.now(UTC)
    db.commit()
    return list_milestones(db, member, project.id)


def _owned_milestone(db: Session, member: Member, project_id: uuid.UUID, milestone_id: uuid.UUID) -> tuple[Project, ProjectMilestone]:
    project = _owned(db, member, project_id, lock=True)
    milestone = db.scalar(
        select(ProjectMilestone).where(ProjectMilestone.id == milestone_id, ProjectMilestone.project_id == project.id, ProjectMilestone.company_id == member.company.id)
    )
    if milestone is None:
        raise ProjectError(404, "Aşama bulunamadı.")
    return project, milestone


def _milestone(row: ProjectMilestone, today: date) -> MilestoneItem:
    done = row.completed_at is not None
    return MilestoneItem(
        id=row.id,
        title=row.title,
        due_date=row.due_date,
        done=done,
        overdue=not done and row.due_date is not None and row.due_date < today,
        completed_at=row.completed_at,
        position=row.position,
    )


def _item(
    project: Project,
    customer: str | None,
    total: int | None,
    done: int | None,
    late: int | None,
    today: date,
    milestones: MilestoneStats | None = None,
    codes: dict[uuid.UUID, str] | None = None,
) -> ProjectItem:
    codes = codes or {}
    all_tasks = int(total or 0)
    finished = int(done or 0)
    milestone_total, milestone_done, next_title, next_due = milestones or (0, 0, None, None)
    return ProjectItem(
        id=project.id,
        name=project.name,
        description=project.description,
        status=project.status,
        customer_id=project.customer_id,
        customer_name=customer,
        quote_id=project.quote_id,
        quote_code=codes.get(project.quote_id) if project.quote_id else None,
        order_id=project.order_id,
        order_code=codes.get(project.order_id) if project.order_id else None,
        start_date=project.start_date,
        due_date=project.due_date,
        working_days_only=project.working_days_only,
        overdue=project.due_date is not None and project.due_date < today and project.status != "completed",
        completed_at=project.completed_at,
        task_total=all_tasks,
        task_done=finished,
        task_overdue=int(late or 0),
        progress=round(finished * 100 / all_tasks) if all_tasks else 0,
        milestone_total=milestone_total,
        milestone_done=milestone_done,
        next_milestone=next_title,
        next_milestone_due=next_due,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )
