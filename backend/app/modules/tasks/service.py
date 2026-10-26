import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Date, String, case, cast, func, literal, or_, select
from sqlalchemy.orm import Session

from app.models.identity import AuditLog, CompanyMembership, User
from app.modules.customers.models import Customer
from app.modules.projects.models import Project
from app.modules.sales.models import SalesOrder
from app.modules.tasks import workflow
from app.modules.tasks.errors import TaskError
from app.modules.tasks.models import Task, TaskDependency
from app.modules.tasks.schemas import (
    Assignee,
    AssigneeLoad,
    TaskRef,
    TodayView,
    TaskDue,
    TaskInput,
    TaskItem,
    TaskPage,
    TaskPriority,
    TaskSort,
    TaskStatus,
    TaskSummary,
)
from app.services.auth import Member
from app.services.automation import emit
from app.services.notifications import notify

_TURKISH = "tr-TR-x-icu"
_RANK = case((Task.priority == "urgent", 3), (Task.priority == "high", 2), (Task.priority == "normal", 1), else_=0)
_ORDER = {
    "due_date": (Task.due_date.asc().nulls_last(), _RANK.desc(), Task.created_at.asc(), Task.id.asc()),
    "-priority": (_RANK.desc(), Task.due_date.asc().nulls_last(), Task.created_at.desc(), Task.id.desc()),
    "-created_at": (Task.created_at.desc(), Task.id.desc()),
    "-completed_at": (Task.completed_at.desc().nulls_last(), Task.id.desc()),
    "title": (Task.title.collate(_TURKISH).asc(), Task.id.asc()),
}


def company_today(db: Session, member: Member) -> date:
    return db.scalar(select(cast(func.timezone(member.company.timezone, func.now()), Date)))


SOURCE_MODULES = {
    "receivable": "finance",
    "payable": "finance",
    "restock": "inventory",
    "quote": "customers",
    "draft": "sales",
    "delivery": "sales",
    "production": "production",
    "project": "projects",
}


def visibility(db: Session, member: Member) -> list:  # type: ignore[type-arg]
    """Hides automatic tasks raised from modules the member cannot see, unless the task is theirs."""
    from app.services.modules import visible_keys

    if member.role in {"owner", "admin"}:
        return []
    hidden = [prefix for prefix, module in SOURCE_MODULES.items() if module not in visible_keys(db, member)]
    if not hidden:
        return []
    return [or_(Task.source_key.is_(None), Task.assignee_user_id == member.user.id, ~or_(*[Task.source_key.like(f"{prefix}:%") for prefix in hidden]))]


def list_tasks(
    db: Session,
    member: Member,
    *,
    query: str | None,
    status: TaskStatus | None,
    priority: TaskPriority | None,
    assignee: str | None,
    due: TaskDue | None,
    sort: TaskSort,
    page: int,
    page_size: int,
    project: str | None = None,
    customer: uuid.UUID | None = None,
    order: uuid.UUID | None = None,
) -> TaskPage:
    today = company_today(db, member)
    filters = [Task.company_id == member.company.id, Task.deleted_at.is_(None), *visibility(db, member)]
    if status is not None:
        filters.append(Task.status == status)
    if priority is not None:
        filters.append(Task.priority == priority)
    if assignee == "me":
        filters.append(Task.assignee_user_id == member.user.id)
    elif assignee == "none":
        filters.append(Task.assignee_user_id.is_(None))
    elif assignee:
        try:
            filters.append(Task.assignee_user_id == uuid.UUID(assignee))
        except ValueError:
            raise TaskError(422, "Sorumlu filtresi geçersiz.") from None
    if project == "none":
        filters.append(Task.project_id.is_(None))
    elif project:
        try:
            filters.append(Task.project_id == uuid.UUID(project))
        except ValueError:
            raise TaskError(422, "Proje filtresi geçersiz.") from None
    if customer is not None:
        filters.append(Task.customer_id == customer)
    if order is not None:
        filters.append(Task.order_id == order)
    if due == "overdue":
        filters.extend([Task.due_date < today, Task.status != "done"])
    elif due == "today":
        filters.append(Task.due_date == today)
    elif due == "week":
        filters.append(Task.due_date.between(today, today + timedelta(days=6)))
    elif due == "none":
        filters.append(Task.due_date.is_(None))
    term = (query or "").strip()
    if term:
        pattern = func.lower(literal(f"%{term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')}%").collate(_TURKISH))
        filters.append(
            or_(
                func.lower(Task.title.collate(_TURKISH)).like(pattern, escape="\\"),
                func.lower(Task.description.collate(_TURKISH)).like(pattern, escape="\\"),
            )
        )
    total = db.scalar(select(func.count()).select_from(Task).where(*filters)) or 0
    rows = db.execute(
        select(Task, User.first_name, User.last_name, Project.name)
        .outerjoin(User, User.id == Task.assignee_user_id)
        .outerjoin(Project, Project.id == Task.project_id)
        .where(*filters)
        .order_by(*_ORDER[sort])
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    links = _links(db, [row[0] for row in rows])
    return TaskPage(
        items=[_item(task, first, last, project_name, today, links) for task, first, last, project_name in rows],
        total=int(total),
        page=page,
        page_size=page_size,
        today=today,
    )


def task_summary(db: Session, member: Member) -> TaskSummary:
    today = company_today(db, member)
    scope = (Task.company_id == member.company.id, Task.deleted_at.is_(None), *visibility(db, member))
    counts = {status: int(count) for status, count in db.execute(select(Task.status, func.count()).where(*scope).group_by(Task.status)).all()}
    open_scope = (*scope, Task.status != "done")
    overdue = db.scalar(select(func.count()).select_from(Task).where(*open_scope, Task.due_date < today)) or 0
    due_today = db.scalar(select(func.count()).select_from(Task).where(*open_scope, Task.due_date == today)) or 0
    return TaskSummary(
        todo=counts.get("todo", 0),
        in_progress=counts.get("in_progress", 0),
        done=counts.get("done", 0),
        overdue=int(overdue),
        due_today=int(due_today),
        today=today,
    )


def list_assignees(db: Session, member: Member) -> list[Assignee]:
    rows = db.execute(
        select(User.id, User.first_name, User.last_name)
        .join(CompanyMembership, CompanyMembership.user_id == User.id)
        .where(CompanyMembership.company_id == member.company.id, CompanyMembership.status == "active")
        .order_by(User.first_name.collate(_TURKISH), User.last_name.collate(_TURKISH))
    ).all()
    return [Assignee(id=user_id, name=f"{first} {last}", me=user_id == member.user.id) for user_id, first, last in rows]


def get_task(db: Session, member: Member, task_id: uuid.UUID) -> TaskItem:
    return _read(db, member, _owned(db, member, task_id))


def create_task(db: Session, member: Member, data: TaskInput) -> TaskItem:
    assignee = _assignee(db, member, data.assignee_id)
    _require_project(db, member, data.project_id)
    _require_links(db, member, data.customer_id, data.order_id)
    now = datetime.now(UTC)
    task = Task(
        id=uuid.uuid4(),
        company_id=member.company.id,
        title=data.title,
        description=data.description,
        status=data.status,
        priority=data.priority,
        due_date=data.due_date,
        assignee_user_id=assignee.id if assignee else None,
        project_id=data.project_id,
        customer_id=data.customer_id,
        order_id=data.order_id,
        completed_at=now if data.status == "done" else None,
        created_by=member.user.id,
    )
    db.add(task)
    db.add(_audit(member, "task.created", task, sorted(data.model_dump(exclude_none=True))))
    _notify_assignee(db, member, task, assignee)
    db.commit()
    return _read(db, member, task)


def update_task(db: Session, member: Member, task_id: uuid.UUID, data: TaskInput) -> TaskItem:
    task = _owned(db, member, task_id, lock=True)
    assignee = _assignee(db, member, data.assignee_id)
    if data.project_id != task.project_id:
        _require_project(db, member, data.project_id)
    values: dict[str, object] = {
        "title": data.title,
        "description": data.description,
        "priority": data.priority,
        "due_date": data.due_date,
        "assignee_user_id": assignee.id if assignee else None,
        "project_id": data.project_id,
    }
    for field in ("customer_id", "order_id"):
        if field in data.model_fields_set:
            values[field] = getattr(data, field)
    _require_links(
        db,
        member,
        data.customer_id if "customer_id" in values and data.customer_id != task.customer_id else None,
        data.order_id if "order_id" in values and data.order_id != task.order_id else None,
    )
    changed = [field for field, value in values.items() if getattr(task, field) != value]
    reassigned = "assignee_user_id" in changed
    for field in changed:
        setattr(task, field, values[field])
    if "project_id" in changed:
        task.milestone_id = None
    if "due_date" in changed and task.duration_days and task.start_date and task.due_date:
        if task.due_date >= task.start_date:
            task.duration_days = min((task.due_date - task.start_date).days + 1, 365)
        else:
            task.start_date = task.due_date - timedelta(days=task.duration_days - 1)
    if task.status != data.status:
        workflow.ensure_can_progress(db, task, data.status)
        _apply_status(task, data.status)
        changed.append("status")
        if data.status == "done":
            _emit_completed(db, member, task)
            workflow.release_dependents(db, member, task)
        workflow.sync_milestone(db, member, task)
    if changed:
        task.updated_at = datetime.now(UTC)
        db.add(_audit(member, "task.updated", task, changed))
        if reassigned:
            _notify_assignee(db, member, task, assignee)
        db.commit()
    return _read(db, member, task)


def set_status(db: Session, member: Member, task_id: uuid.UUID, status: TaskStatus) -> TaskItem:
    task = _owned(db, member, task_id, lock=True)
    if task.status != status:
        workflow.ensure_can_progress(db, task, status)
        previous = task.status
        _apply_status(task, status)
        task.updated_at = datetime.now(UTC)
        db.add(_audit(member, "task.status_changed", task, [], {"from": previous, "to": status}))
        if status == "done":
            _emit_completed(db, member, task)
            workflow.release_dependents(db, member, task)
        workflow.sync_milestone(db, member, task)
        db.commit()
    return _read(db, member, task)


def change_dependencies(db: Session, member: Member, task_id: uuid.UUID, depends_on: list[uuid.UUID]) -> TaskItem:
    task = _owned(db, member, task_id, lock=True)
    workflow.set_dependencies(db, member, task, depends_on)
    db.commit()
    return _read(db, member, task)


def items_for(db: Session, member: Member, task_ids: list[uuid.UUID]) -> list[TaskItem]:
    if not task_ids:
        return []
    today = company_today(db, member)
    rows = db.execute(
        select(Task, User.first_name, User.last_name, Project.name)
        .outerjoin(User, User.id == Task.assignee_user_id)
        .outerjoin(Project, Project.id == Task.project_id)
        .where(Task.id.in_(task_ids), Task.company_id == member.company.id)
    ).all()
    links = _links(db, [row[0] for row in rows])
    order = {task_id: index for index, task_id in enumerate(task_ids)}
    items = [_item(task, first, last, project_name, today, links) for task, first, last, project_name in rows]
    return sorted(items, key=lambda item: order[item.id])


def today_view(db: Session, member: Member) -> TodayView:
    today = company_today(db, member)
    mine = (Task.company_id == member.company.id, Task.deleted_at.is_(None), Task.status != "done", Task.assignee_user_id == member.user.id)

    def ids(*conditions: object, order: tuple[object, ...] = (Task.due_date.asc().nulls_last(), _RANK.desc()), limit: int = 30) -> list[uuid.UUID]:
        return list(db.scalars(select(Task.id).where(*mine, *conditions).order_by(*order).limit(limit)))  # type: ignore[arg-type]

    blocked_ids = set(
        db.scalars(
            select(TaskDependency.task_id)
            .join(Task, Task.id == TaskDependency.depends_on_id)
            .where(TaskDependency.company_id == member.company.id, Task.status != "done", Task.deleted_at.is_(None))
        )
    )
    open_ids = ids()
    waiting = [task_id for task_id in open_ids if task_id in blocked_ids]
    released = list(
        db.scalars(
            select(Task.id)
            .join(AuditLog, AuditLog.entity_id == cast(Task.id, String))
            .where(*mine, AuditLog.company_id == member.company.id, AuditLog.action == "task.unblocked", AuditLog.created_at >= func.now() - timedelta(days=7))
            .distinct()
        )
    )
    names = {user_id: f"{first} {last}" for user_id, first, last in db.execute(
        select(User.id, User.first_name, User.last_name).join(CompanyMembership, CompanyMembership.user_id == User.id).where(CompanyMembership.company_id == member.company.id)
    ).all()}
    load = [
        AssigneeLoad(assignee_id=row["assignee_id"], name=names.get(row["assignee_id"], "Atanmamış") if row["assignee_id"] else "Atanmamış", **{k: row[k] for k in ("open", "overdue", "this_week")})  # type: ignore[arg-type]
        for row in workflow.load_counts(db, member, today)
    ]
    load.sort(key=lambda item: (-item.overdue, -item.open))
    return TodayView(
        today=today,
        overdue=items_for(db, member, ids(Task.due_date < today)),
        due_today=items_for(db, member, ids(Task.due_date == today)),
        in_progress=items_for(db, member, ids(Task.status == "in_progress", or_(Task.due_date.is_(None), Task.due_date > today))),
        upcoming=items_for(
            db,
            member,
            [
                task_id
                for task_id in ids(Task.status == "todo", Task.due_date > today, Task.due_date <= today + timedelta(days=7))
                if task_id not in blocked_ids and task_id not in released
            ],
        ),
        waiting=items_for(db, member, waiting),
        unblocked=items_for(db, member, [task_id for task_id in released if task_id not in blocked_ids]),
        load=load,
    )


def _emit_completed(db: Session, member: Member, task: Task) -> None:
    emit(
        db,
        member,
        "task.completed",
        {
            "id": str(task.id),
            "title": task.title,
            "priority": task.priority,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "project_id": str(task.project_id) if task.project_id else None,
            "assignee_id": str(task.assignee_user_id) if task.assignee_user_id else None,
            "completed_by": f"{member.user.first_name} {member.user.last_name}",
        },
    )


def delete_task(db: Session, member: Member, task_id: uuid.UUID) -> None:
    task = _owned(db, member, task_id, lock=True)
    now = datetime.now(UTC)
    task.deleted_at = now
    task.updated_at = now
    db.add(_audit(member, "task.deleted", task, []))
    db.commit()


def _apply_status(task: Task, status: str) -> None:
    task.status = status
    if status == "done":
        task.completed_at = datetime.now(UTC)
    else:
        task.completed_at = None


def _assignee(db: Session, member: Member, user_id: uuid.UUID | None) -> User | None:
    if user_id is None:
        return None
    user = db.scalar(
        select(User)
        .join(CompanyMembership, CompanyMembership.user_id == User.id)
        .where(User.id == user_id, CompanyMembership.company_id == member.company.id, CompanyMembership.status == "active")
    )
    if user is None:
        raise TaskError(422, "Seçilen sorumlu bu çalışma alanında değil.")
    return user


def _require_project(db: Session, member: Member, project_id: uuid.UUID | None) -> None:
    if project_id is None:
        return
    exists = db.scalar(
        select(Project.id).where(Project.id == project_id, Project.company_id == member.company.id, Project.deleted_at.is_(None))
    )
    if exists is None:
        raise TaskError(422, "Seçilen proje bulunamadı.")


def validate_links(
    db: Session, member: Member, assignee_id: uuid.UUID | None, customer_id: uuid.UUID | None, order_id: uuid.UUID | None, project_id: uuid.UUID | None
) -> None:
    _assignee(db, member, assignee_id)
    _require_project(db, member, project_id)
    _require_links(db, member, customer_id, order_id)


def _require_links(db: Session, member: Member, customer_id: uuid.UUID | None, order_id: uuid.UUID | None) -> None:
    if customer_id is not None:
        found = db.scalar(select(Customer.id).where(Customer.id == customer_id, Customer.company_id == member.company.id, Customer.deleted_at.is_(None)))
        if found is None:
            raise TaskError(422, "Seçilen müşteri bulunamadı.")
    if order_id is not None:
        found = db.scalar(select(SalesOrder.id).where(SalesOrder.id == order_id, SalesOrder.company_id == member.company.id))
        if found is None:
            raise TaskError(422, "Seçilen sipariş bulunamadı.")


def _links(db: Session, tasks: list[Task]) -> dict[str, dict]:  # type: ignore[type-arg]
    customers = {task.customer_id for task in tasks if task.customer_id}
    orders = {task.order_id for task in tasks if task.order_id}
    return {
        "deps": workflow.prerequisites(db, [task.id for task in tasks]),
        "customer": dict(db.execute(select(Customer.id, Customer.name).where(Customer.id.in_(customers))).all()) if customers else {},
        "order": {order_id: f"SP-{number:04d}" for order_id, number in db.execute(select(SalesOrder.id, SalesOrder.number).where(SalesOrder.id.in_(orders))).all()}
        if orders
        else {},
    }


def _notify_assignee(db: Session, member: Member, task: Task, assignee: User | None) -> None:
    if assignee is None or assignee.id == member.user.id:
        return
    notify(
        db,
        member,
        user_id=assignee.id,
        category="tasks",
        title="Size yeni bir görev atandı.",
        body=f"{member.user.first_name} {member.user.last_name}: {task.title}",
        link="/panel/gorevler?sorumlu=me",
        dedupe_key=f"task.assigned:{task.id}:{assignee.id}",
    )


def _owned(db: Session, member: Member, task_id: uuid.UUID, *, lock: bool = False) -> Task:
    statement = select(Task).where(Task.id == task_id, Task.company_id == member.company.id, Task.deleted_at.is_(None), *visibility(db, member))
    if lock:
        statement = statement.with_for_update()
    task = db.scalar(statement)
    if task is None:
        raise TaskError(404, "Görev bulunamadı.")
    return task


def _audit(member: Member, action: str, task: Task, fields: list[str], extra: dict[str, object] | None = None) -> AuditLog:
    return AuditLog(
        company_id=member.company.id,
        actor_user_id=member.user.id,
        action=action,
        entity_type="task",
        entity_id=str(task.id),
        summary={"fields": fields, **(extra or {})},
        source="api",
    )


def _read(db: Session, member: Member, task: Task) -> TaskItem:
    db.refresh(task)
    names = db.execute(select(User.first_name, User.last_name).where(User.id == task.assignee_user_id)).first() if task.assignee_user_id else None
    project_name = db.scalar(select(Project.name).where(Project.id == task.project_id)) if task.project_id else None
    return _item(task, names[0] if names else None, names[1] if names else None, project_name, company_today(db, member), _links(db, [task]))


def _item(task: Task, first: str | None, last: str | None, project_name: str | None, today: date, links: dict[str, dict]) -> TaskItem:  # type: ignore[type-arg]
    deps = links["deps"].get(task.id, [])
    return TaskItem(
        depends_on=[TaskRef(id=dep_id, title=title, status=status) for dep_id, title, status in deps],
        blocked=task.status != "done" and any(status != "done" for _, _, status in deps),
        automatic=task.source_key is not None,
        customer_id=task.customer_id,
        customer_name=links["customer"].get(task.customer_id) if task.customer_id else None,
        order_id=task.order_id,
        order_code=links["order"].get(task.order_id) if task.order_id else None,
        id=task.id,
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority,
        due_date=task.due_date,
        overdue=task.due_date is not None and task.due_date < today and task.status != "done",
        assignee_id=task.assignee_user_id,
        assignee_name=f"{first} {last}" if first else None,
        project_id=task.project_id,
        project_name=project_name,
        completed_at=task.completed_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )
