"""Read-only customer overview assembled from the modules that are enabled."""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.customers.models import Customer
from app.modules.customers.schemas import (
    CustomerOverview,
    OverviewFinance,
    OverviewLink,
    OverviewMoney,
    OverviewTask,
    OverviewTimeline,
)
from app.modules.finance.models import OPEN_STATUSES, FinancialRecord
from app.modules.projects.models import Project
from app.modules.quotes.models import Quote
from app.modules.sales.models import SalesOrder
from app.modules.tasks.models import Task
from app.modules.tasks.service import company_today
from app.services.auth import Member
from app.services.modules import visible_keys

ORDER_LABELS = {"draft": "Taslak", "confirmed": "Onaylandı", "fulfilled": "Teslim edildi", "cancelled": "İptal edildi"}
QUOTE_LABELS = {"draft": "Taslak", "sent": "Gönderildi", "accepted": "Kabul edildi", "rejected": "Reddedildi"}
PROJECT_LABELS = {"planned": "Planlandı", "active": "Devam ediyor", "on_hold": "Beklemede", "completed": "Tamamlandı"}
RECENT = 8


def _money(value: Decimal | None) -> str:
    return f"{(value or Decimal(0)):.2f}"


def _totals(rows: list[tuple[str, Decimal | None]]) -> list[OverviewMoney]:
    ordered = sorted(rows, key=lambda row: (row[0] != "TRY", row[0]))
    return [OverviewMoney(currency=currency, amount=_money(amount)) for currency, amount in ordered if amount]


def customer_overview(db: Session, member: Member, customer: Customer) -> CustomerOverview:
    enabled = visible_keys(db, member)
    company = member.company.id
    today = company_today(db, member)
    timeline: list[OverviewTimeline] = [OverviewTimeline(kind="customer", label="Müşteri kaydı açıldı", at=customer.created_at, link=None)]
    overview = CustomerOverview(enabled=sorted(enabled & {"sales", "customers", "projects", "tasks", "finance"}), timeline=[])

    if "sales" in enabled:
        scope = (SalesOrder.company_id == company, SalesOrder.customer_id == customer.id)
        orders = db.scalars(select(SalesOrder).where(*scope).order_by(SalesOrder.order_date.desc(), SalesOrder.number.desc()).limit(RECENT)).all()
        overview.order_count = int(db.scalar(select(func.count()).select_from(SalesOrder).where(*scope)) or 0)
        overview.open_orders = int(db.scalar(select(func.count()).select_from(SalesOrder).where(*scope, SalesOrder.status.in_(("draft", "confirmed")))) or 0)
        overview.revenue = _totals(
            db.execute(
                select(SalesOrder.currency, func.sum(SalesOrder.total)).where(*scope, SalesOrder.status.in_(("confirmed", "fulfilled"))).group_by(SalesOrder.currency)
            ).all()
        )
        overview.orders = [
            OverviewLink(
                id=order.id,
                code=f"SP-{order.number:04d}",
                status=order.status,
                status_label=ORDER_LABELS[order.status],
                when=order.order_date,
                amount=_money(order.total),
                currency=order.currency,
            )
            for order in orders
        ]
        timeline += [OverviewTimeline(kind="order", label=f"SP-{order.number:04d} siparişi oluşturuldu", at=order.created_at, link="/panel/satis") for order in orders]

    if "customers" in enabled:
        scope = (Quote.company_id == company, Quote.customer_id == customer.id)
        quotes = db.scalars(select(Quote).where(*scope).order_by(Quote.quote_date.desc(), Quote.number.desc()).limit(RECENT)).all()
        overview.open_quotes = int(db.scalar(select(func.count()).select_from(Quote).where(*scope, Quote.status.in_(("draft", "sent")))) or 0)
        overview.quotes = [
            OverviewLink(
                id=quote.id,
                code=f"TK-{quote.number:04d}",
                status=quote.status,
                status_label=QUOTE_LABELS[quote.status],
                when=quote.quote_date,
                amount=_money(quote.total),
                currency=quote.currency,
            )
            for quote in quotes
        ]
        timeline += [
            OverviewTimeline(kind="quote", label=f"TK-{quote.number:04d} teklifi hazırlandı", at=quote.created_at, link="/panel/musteriler?bolum=teklifler")
            for quote in quotes
        ]

    if "projects" in enabled:
        projects = db.scalars(
            select(Project).where(Project.company_id == company, Project.customer_id == customer.id, Project.deleted_at.is_(None)).order_by(Project.created_at.desc())
        ).all()
        overview.projects = [
            OverviewLink(id=project.id, code=project.name, status=project.status, status_label=PROJECT_LABELS[project.status], when=project.due_date)
            for project in projects
        ]
        timeline += [OverviewTimeline(kind="project", label=f"“{project.name}” projesi açıldı", at=project.created_at, link="/panel/projeler") for project in projects]

    if "tasks" in enabled:
        tasks = db.scalars(
            select(Task)
            .where(Task.company_id == company, Task.customer_id == customer.id, Task.deleted_at.is_(None), Task.status != "done")
            .order_by(Task.due_date.asc().nulls_last(), Task.created_at)
            .limit(20)
        ).all()
        overview.open_tasks = [
            OverviewTask(id=task.id, title=task.title, status=task.status, due_date=task.due_date, overdue=task.due_date is not None and task.due_date < today)
            for task in tasks
        ]

    if "finance" in enabled:
        scope = (FinancialRecord.company_id == company, FinancialRecord.customer_id == customer.id, FinancialRecord.kind == "income")
        open_ = FinancialRecord.status.in_(OPEN_STATUSES)
        pending = db.scalars(select(FinancialRecord).where(*scope, open_).order_by(FinancialRecord.due_date.asc().nulls_last())).all()
        overview.finance = OverviewFinance(
            receivable=_totals(
                db.execute(
                    select(FinancialRecord.currency, func.sum(FinancialRecord.amount - FinancialRecord.paid_amount)).where(*scope, open_).group_by(FinancialRecord.currency)
                ).all()
            ),
            collected=_totals(
                db.execute(
                    select(FinancialRecord.currency, func.sum(FinancialRecord.paid_amount))
                    .where(*scope, FinancialRecord.status != "cancelled", FinancialRecord.paid_amount > 0)
                    .group_by(FinancialRecord.currency)
                ).all()
            ),
            overdue=sum(1 for record in pending if record.due_date is not None and record.due_date < today),
            pending=[
                OverviewLink(
                    id=record.id,
                    code=record.description,
                    status="overdue" if record.due_date is not None and record.due_date < today else "pending",
                    status_label="Vadesi geçti"
                    if record.due_date is not None and record.due_date < today
                    else "Kısmen ödendi"
                    if record.status == "partial"
                    else "Bekliyor",
                    when=record.due_date,
                    amount=_money(record.amount - record.paid_amount),
                    currency=record.currency,
                )
                for record in pending[:RECENT]
            ],
        )

    overview.timeline = sorted(timeline, key=lambda item: item.at, reverse=True)[:15]
    return overview
