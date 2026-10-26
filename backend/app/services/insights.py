"""Business signals across modules and the automatic tasks created from them.

A signal is a condition that needs someone's attention ("this receivable is overdue").
Each signal has a stable key. With autopilot on, an open task is kept for every signal:
it is created when the signal appears and completed automatically when the signal goes
away. A task the user completes by hand is not recreated for three days, so finishing a
follow-up call does not immediately produce the same task again.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.identity import AuditLog, CompanyMembership, User
from app.modules.customers.models import Customer
from app.modules.finance.models import OPEN_STATUSES, FinancialRecord
from app.modules.inventory.service import quantity_label, reorder_suggestions
from app.modules.production.models import ProductionOrder
from app.modules.projects.models import Project
from app.modules.quotes.models import Quote
from app.modules.sales.models import SalesOrder
from app.modules.tasks.models import AutopilotSettings, Task
from app.modules.tasks.service import company_today
from app.services.auth import Member
from app.services.modules import enabled_keys, visible_keys

KINDS = {
    "receivable_overdue": ("finance", "Vadesi geçen tahsilat"),
    "payable_due": ("finance", "Yaklaşan veya geciken ödeme"),
    "restock": ("inventory", "Stok tamamlama"),
    "quote_followup": ("customers", "Cevap bekleyen teklif"),
    "draft_order": ("sales", "Bekleyen taslak sipariş"),
    "late_delivery": ("sales", "Geciken teslimat"),
    "production_start": ("production", "Başlaması gereken üretim"),
    "project_late": ("projects", "Teslimi kayan proje"),
    "auto_assign": ("tasks", "Sorumlusu olmayan görevleri iş yüküne göre dağıt"),
}
SIGNAL_KINDS = [key for key in KINDS if key != "auto_assign"]
SNOOZE = timedelta(days=3)
RUN_EVERY = timedelta(minutes=5)
_SEVERITY = {"high": 0, "medium": 1, "low": 2}


@dataclass
class Signal:
    key: str
    kind: str
    severity: str
    title: str
    detail: str
    link: str
    task_title: str
    priority: str = "normal"
    due: date | None = None
    owner: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    order_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    extra: dict[str, object] = field(default_factory=dict)


def _money(value: Decimal, currency: str) -> str:
    text = f"{value:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return f"{text} {'₺' if currency == 'TRY' else currency}"


def _day(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def collect(db: Session, member: Member, *, whole_company: bool = False) -> list[Signal]:
    """Signals from the modules the person may see; the task sync needs every enabled module."""
    enabled = enabled_keys(db, member) if whole_company else visible_keys(db, member)
    today = company_today(db, member)
    company = member.company.id
    signals: list[Signal] = []

    if "finance" in enabled:
        rows = db.execute(
            select(FinancialRecord, Customer.name)
            .outerjoin(Customer, Customer.id == FinancialRecord.customer_id)
            .where(FinancialRecord.company_id == company, FinancialRecord.status.in_(OPEN_STATUSES), FinancialRecord.due_date.is_not(None))
            .order_by(FinancialRecord.due_date)
            .limit(60)
        ).all()
        for record, customer in rows:
            due = record.due_date
            remaining = record.amount - record.paid_amount
            party = customer or record.counterparty
            if record.kind == "income" and due < today:  # type: ignore[operator]
                late = (today - due).days  # type: ignore[operator]
                signals.append(
                    Signal(
                        key=f"receivable:{record.id}",
                        kind="receivable_overdue",
                        severity="high" if late > 7 else "medium",
                        title=f"{party or record.description}: {_money(remaining, record.currency)} tahsilatın vadesi {late} gün geçti",
                        detail=f"“{record.description}” için vade {_day(due)} idi.",  # type: ignore[arg-type]
                        link="/panel/finans?gorunum=vadeler",
                        task_title=f"Tahsilatı takip et: {party or record.description}"[:200],
                        priority="high",
                        due=today,
                        owner=record.created_by,
                        customer_id=record.customer_id,
                        order_id=record.order_id,
                    )
                )
            elif record.kind == "expense" and due <= today + timedelta(days=3):  # type: ignore[operator]
                late = due < today  # type: ignore[operator]
                signals.append(
                    Signal(
                        key=f"payable:{record.id}",
                        kind="payable_due",
                        severity="high" if late else "medium",
                        title=f"{record.description}: {_money(remaining, record.currency)} ödeme {'gecikti' if late else 'yaklaşıyor'}",
                        detail=f"Vade {_day(due)}." + (f" Alıcı: {party}." if party else ""),  # type: ignore[arg-type]
                        link="/panel/finans?gorunum=vadeler",
                        task_title=f"Ödemeyi yap: {record.description}"[:200],
                        priority="high" if late else "normal",
                        due=max(due, today) if due else today,  # type: ignore[type-var]
                        owner=record.created_by,
                    )
                )

    if "inventory" in enabled:
        for item in reorder_suggestions(db, member)[:15]:
            produce = item.action == "produce" and "production" in enabled
            signals.append(
                Signal(
                    key=f"restock:{item.product_id}",
                    kind="restock",
                    severity="high" if Decimal(item.expected) < 0 else "medium",
                    title=f"{item.name}: {quantity_label(Decimal(item.suggested))} {item.unit} {'üretilmeli' if produce else 'alınmalı'}",
                    detail=" ".join(item.reasons),
                    link="/panel/stok",
                    task_title=f"{'Üretim planla' if produce else 'Satın alma yap'}: {item.name} ({quantity_label(Decimal(item.suggested))} {item.unit})"[:200],
                    priority="high" if Decimal(item.expected) < 0 else "normal",
                    due=today,
                )
            )

    if "customers" in enabled:
        rows = db.execute(
            select(Quote, Customer.name)
            .join(Customer, Customer.id == Quote.customer_id)
            .where(Quote.company_id == company, Quote.status == "sent")
            .order_by(Quote.sent_at)
            .limit(30)
        ).all()
        for quote, customer in rows:
            sent = quote.sent_at.date() if quote.sent_at else quote.quote_date
            waited = (today - sent).days
            expiring = quote.valid_until is not None and quote.valid_until <= today + timedelta(days=2)
            if waited < 3 and not expiring:
                continue
            code = f"TK-{quote.number:04d}"
            reason = f"Geçerlilik {_day(quote.valid_until)} tarihinde bitiyor." if expiring and quote.valid_until else f"{waited} gündür cevap yok."
            signals.append(
                Signal(
                    key=f"quote:{quote.id}",
                    kind="quote_followup",
                    severity="medium" if expiring else "low",
                    title=f"{code} teklifi {customer} için cevap bekliyor",
                    detail=reason,
                    link="/panel/musteriler?bolum=teklifler",
                    task_title=f"Teklifi takip et: {code} · {customer}"[:200],
                    due=today,
                    owner=quote.created_by,
                    customer_id=quote.customer_id,
                )
            )

    if "sales" in enabled:
        rows = db.execute(
            select(SalesOrder, Customer.name)
            .join(Customer, Customer.id == SalesOrder.customer_id)
            .where(SalesOrder.company_id == company, SalesOrder.status.in_(("draft", "confirmed")))
            .order_by(SalesOrder.created_at)
            .limit(40)
        ).all()
        for order, customer in rows:
            code = f"SP-{order.number:04d}"
            if order.status == "draft":
                age = (today - order.created_at.date()).days
                if age < 2:
                    continue
                signals.append(
                    Signal(
                        key=f"draft:{order.id}",
                        kind="draft_order",
                        severity="low",
                        title=f"{code} ({customer}) {age} gündür taslakta",
                        detail="Onaylanmayan sipariş stoğu ayırmaz ve teslimata geçmez.",
                        link="/panel/satis",
                        task_title=f"Taslak siparişi onayla veya iptal et: {code}"[:200],
                        due=today,
                        owner=order.created_by,
                        customer_id=order.customer_id,
                        order_id=order.id,
                    )
                )
            else:
                since = (order.confirmed_at or order.created_at).date()
                age = (today - since).days
                if age < 7:
                    continue
                signals.append(
                    Signal(
                        key=f"delivery:{order.id}",
                        kind="late_delivery",
                        severity="high" if age > 14 else "medium",
                        title=f"{code} ({customer}) {age} gündür teslim bekliyor",
                        detail="Sipariş onaylandı ama henüz teslim edilmedi.",
                        link="/panel/satis",
                        task_title=f"Teslimatı planla: {code} · {customer}"[:200],
                        priority="high" if age > 14 else "normal",
                        due=today,
                        owner=order.created_by,
                        customer_id=order.customer_id,
                        order_id=order.id,
                    )
                )

    if "production" in enabled:
        from app.modules.inventory.models import Product

        rows = db.execute(
            select(ProductionOrder, Product.name)
            .join(Product, Product.id == ProductionOrder.product_id)
            .where(ProductionOrder.company_id == company, ProductionOrder.status == "planned", ProductionOrder.planned_date <= today)
            .order_by(ProductionOrder.planned_date)
            .limit(20)
        ).all()
        for job, product in rows:
            code = f"UE-{job.number:04d}"
            late = (today - job.planned_date).days if job.planned_date else 0
            signals.append(
                Signal(
                    key=f"production:{job.id}",
                    kind="production_start",
                    severity="medium" if late > 0 else "low",
                    title=f"{code} {product} üretimi {'bugün başlamalı' if late == 0 else f'{late} gün gecikti'}",
                    detail=f"Plan tarihi {_day(job.planned_date)}." if job.planned_date else "Plan tarihi geldi.",
                    link="/panel/uretim",
                    task_title=f"Üretimi başlat: {code} · {product}"[:200],
                    priority="high" if late > 0 else "normal",
                    due=today,
                    owner=job.created_by,
                    order_id=job.sales_order_id,
                    project_id=job.project_id,
                )
            )

    if "projects" in enabled:
        from app.modules.projects.planning import reschedule

        projects = db.scalars(
            select(Project)
            .where(Project.company_id == company, Project.deleted_at.is_(None), Project.status.in_(("planned", "active")), Project.due_date.is_not(None))
            .limit(20)
        ).all()
        for project in projects:
            plan = reschedule(db, member, project, today, apply=False)
            if plan.delay_days <= 0:
                continue
            signals.append(
                Signal(
                    key=f"project:{project.id}",
                    kind="project_late",
                    severity="high" if plan.delay_days > 3 else "medium",
                    title=f"{project.name} teslim tarihini {plan.delay_days} gün aşıyor",
                    detail=f"Bağımlılıklara göre en erken bitiş {_day(plan.projected_finish)}, hedef {_day(project.due_date)}."  # type: ignore[arg-type]
                    if plan.projected_finish
                    else "Plan hedefi aşıyor.",
                    link="/panel/projeler",
                    task_title=f"Proje planını gözden geçir: {project.name}"[:200],
                    priority="high",
                    due=today,
                    owner=project.created_by,
                    customer_id=project.customer_id,
                    project_id=project.id,
                )
            )

    signals.sort(key=lambda signal: (_SEVERITY[signal.severity], signal.kind))
    return signals


def settings(db: Session, member: Member) -> AutopilotSettings:
    found = db.get(AutopilotSettings, member.company.id)
    if found is None:
        savepoint = db.begin_nested()
        db.add(AutopilotSettings(company_id=member.company.id, enabled=True, kinds=list(SIGNAL_KINDS)))
        try:
            savepoint.commit()
        except IntegrityError:
            savepoint.rollback()
        found = db.get(AutopilotSettings, member.company.id)
    return found  # type: ignore[return-value]


def _members(db: Session, member: Member) -> tuple[set[uuid.UUID], uuid.UUID | None]:
    rows = db.execute(
        select(CompanyMembership.user_id, CompanyMembership.role).where(
            CompanyMembership.company_id == member.company.id, CompanyMembership.status == "active"
        )
    ).all()
    active = {user_id for user_id, _ in rows}
    owner = next((user_id for user_id, role in rows if role == "owner"), None)
    return active, owner


def sync_tasks(db: Session, member: Member, *, force: bool = False) -> dict[str, int]:
    """Create tasks for new signals and complete tasks whose signal has gone. Commits."""
    if "tasks" not in enabled_keys(db, member):
        return {"created": 0, "resolved": 0}
    config = settings(db, member)
    now = datetime.now(UTC)
    if not force and config.last_run_at is not None and now - config.last_run_at < RUN_EVERY:
        db.commit()
        return {"created": 0, "resolved": 0}
    config.last_run_at = now
    chosen = set(config.kinds)
    signals = [signal for signal in collect(db, member, whole_company=True) if signal.kind in chosen] if config.enabled and chosen & set(SIGNAL_KINDS) else []
    wanted = {signal.key: signal for signal in signals}
    open_tasks = {
        task.source_key: task
        for task in db.scalars(
            select(Task).where(Task.company_id == member.company.id, Task.source_key.is_not(None), Task.status != "done", Task.deleted_at.is_(None))
        )
    }
    recent_done = set(
        db.scalars(
            select(Task.source_key).where(
                Task.company_id == member.company.id, Task.source_key.in_(list(wanted) or [""]), Task.status == "done", Task.completed_at > now - SNOOZE
            )
        )
    )
    active, owner = _members(db, member)
    created = resolved = 0
    for key, signal in wanted.items():
        if key in open_tasks or key in recent_done:
            continue
        assignee = signal.owner if signal.owner in active else config.default_assignee_id if config.default_assignee_id in active else owner
        task = Task(
            id=uuid.uuid4(),
            company_id=member.company.id,
            title=signal.task_title,
            description=f"{signal.title}. {signal.detail}"[:4000],
            status="todo",
            priority=signal.priority,
            due_date=signal.due,
            assignee_user_id=assignee,
            customer_id=signal.customer_id,
            order_id=signal.order_id,
            project_id=signal.project_id,
            source_key=key,
            created_by=member.user.id,
        )
        savepoint = db.begin_nested()
        db.add(task)
        try:
            savepoint.commit()
        except IntegrityError:
            savepoint.rollback()
            continue
        db.add(_audit(member, "task.auto_created", task, {"kind": signal.kind, "reason": signal.title}))
        created += 1
    for key, task in open_tasks.items():
        if key in wanted or key is None:
            continue
        task.status = "done"
        task.completed_at = now
        task.updated_at = now
        db.add(_audit(member, "task.auto_resolved", task, {"reason": "Görevi doğuran durum ortadan kalktı."}))
        resolved += 1
    if config.enabled and "auto_assign" in config.kinds:
        _distribute(db, member, active)
    db.commit()
    return {"created": created, "resolved": resolved}


def _distribute(db: Session, member: Member, active: set[uuid.UUID]) -> None:
    """Give each unassigned open task to the active member with the fewest open tasks."""
    if not active:
        return
    open_scope = (Task.company_id == member.company.id, Task.status != "done", Task.deleted_at.is_(None))
    load = {user_id: 0 for user_id in active}
    for user_id in db.scalars(select(Task.assignee_user_id).where(*open_scope, Task.assignee_user_id.in_(active))):
        load[user_id] += 1  # type: ignore[index]
    names = {user_id: f"{first} {last}" for user_id, first, last in db.execute(select(User.id, User.first_name, User.last_name).where(User.id.in_(active))).all()}
    for task in db.scalars(select(Task).where(*open_scope, Task.assignee_user_id.is_(None)).order_by(Task.due_date.asc().nulls_last(), Task.created_at).limit(50)):
        chosen = min(load, key=lambda user_id: (load[user_id], names.get(user_id, "")))
        task.assignee_user_id = chosen
        task.updated_at = datetime.now(UTC)
        load[chosen] += 1
        db.add(_audit(member, "task.auto_assigned", task, {"reason": f"{names.get(chosen, 'Ekip üyesi')} kişisine iş yüküne göre atandı."}))


def _audit(member: Member, action: str, task: Task, summary: dict[str, object]) -> AuditLog:
    return AuditLog(
        company_id=member.company.id,
        actor_user_id=member.user.id,
        action=action,
        entity_type="task",
        entity_id=str(task.id),
        summary={"fields": [], **summary},
        source="automation",
    )


def describe(db: Session, member: Member) -> dict[str, object]:
    """Signals with the automatic task attached to each, for the home page."""
    signals = collect(db, member)
    keys = [signal.key for signal in signals]
    tasks = (
        {
            task.source_key: task
            for task in db.scalars(select(Task).where(Task.company_id == member.company.id, Task.source_key.in_(keys), Task.status != "done", Task.deleted_at.is_(None)))
        }
        if keys
        else {}
    )
    names = {}
    assignees = {task.assignee_user_id for task in tasks.values() if task.assignee_user_id}
    if assignees:
        names = {user_id: f"{first} {last}" for user_id, first, last in db.execute(select(User.id, User.first_name, User.last_name).where(User.id.in_(assignees))).all()}
    config = db.get(AutopilotSettings, member.company.id)
    return {
        "items": [
            {
                "key": signal.key,
                "kind": signal.kind,
                "module": KINDS[signal.kind][0],
                "severity": signal.severity,
                "title": signal.title,
                "detail": signal.detail,
                "link": signal.link,
                "task_id": tasks[signal.key].id if signal.key in tasks else None,
                "task_assignee": names.get(tasks[signal.key].assignee_user_id) if signal.key in tasks and tasks[signal.key].assignee_user_id else None,
            }
            for signal in signals
        ],
        "autopilot": bool(config.enabled) if config else True,
    }
