"""Weekly status digest e-mail, sent on Monday from 09:00 company time by the scheduled pass."""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.identity import Company, User
from app.models.mail import EmailMessage
from app.modules.finance.models import OPEN_STATUSES, FinancialPayment, FinancialRecord
from app.modules.inventory.models import Product
from app.modules.inventory.service import CRITICAL_FILTER, LOW_FILTER, critical_level, quantity_label
from app.modules.projects.models import Project
from app.modules.sales.models import SalesOrder
from app.modules.tasks.models import Task
from app.services import mail
from app.services.auth import Member
from app.services.modules import visible_keys
from app.services.notifications import MANAGERS, wants_email

DIGEST_WEEKDAY = 0
DIGEST_HOUR = 9
LIST_LIMIT = 5
_SYMBOLS = {"TRY": "₺", "USD": "$", "EUR": "€"}
_MONTHS = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")


@dataclass
class Section:
    title: str
    link: str
    lines: list[str] = field(default_factory=list)


def money(value: Decimal, currency: str) -> str:
    whole, _, cents = f"{abs(value):,.2f}".partition(".")
    text = f"{_SYMBOLS.get(currency, currency + ' ')}{whole.replace(',', '.')},{cents}"
    return f"-{text}" if value < 0 else text


def _amounts(rows: list[tuple[str, Decimal]]) -> str:
    return " · ".join(money(Decimal(amount), currency) for currency, amount in rows if amount) or money(Decimal(0), "TRY")


def _day(value: date) -> str:
    return f"{value.day} {_MONTHS[value.month - 1]}"


def local_now(db: Session, company: Company) -> datetime:
    return db.scalar(select(func.timezone(company.timezone, func.now())))


def week_start(now: datetime) -> date | None:
    """The Monday the digest belongs to, or None while it is not yet time to send."""
    if now.weekday() != DIGEST_WEEKDAY or now.hour < DIGEST_HOUR:
        return None
    return now.date()


def _task_section(db: Session, member: Member, today: date) -> Section:
    section = Section("Görevleriniz", "/panel/gorevler")
    scope = (
        Task.company_id == member.company.id,
        Task.assignee_user_id == member.user.id,
        Task.deleted_at.is_(None),
        Task.status != "done",
        Task.due_date.is_not(None),
    )
    late = list(db.scalars(select(Task).where(*scope, Task.due_date < today).order_by(Task.due_date, Task.title)))
    week = list(db.scalars(select(Task).where(*scope, Task.due_date >= today, Task.due_date <= today + timedelta(days=6)).order_by(Task.due_date, Task.title)))
    if late:
        section.lines.append(f"{len(late)} geciken görev: " + ", ".join(f"{task.title} ({_day(task.due_date)})" for task in late[:LIST_LIMIT]))  # type: ignore[arg-type]
    if week:
        section.lines.append(f"Bu hafta teslim {len(week)} görev: " + ", ".join(f"{task.title} ({_day(task.due_date)})" for task in week[:LIST_LIMIT]))  # type: ignore[arg-type]
    return section


def _sales_section(db: Session, company_id: uuid.UUID, start: date) -> Section:
    section = Section("Satış", "/panel/satis")
    previous = (start - timedelta(days=7), start - timedelta(days=1))
    sold = db.execute(
        select(SalesOrder.currency, func.count(), func.sum(SalesOrder.total))
        .where(SalesOrder.company_id == company_id, SalesOrder.status != "cancelled", SalesOrder.order_date.between(*previous))
        .group_by(SalesOrder.currency)
    ).all()
    count = sum(int(row[1]) for row in sold)
    if count:
        section.lines.append(f"Geçen hafta {count} sipariş, toplam {_amounts([(row[0], row[2]) for row in sold])}.")
    waiting = db.scalar(select(func.count()).select_from(SalesOrder).where(SalesOrder.company_id == company_id, SalesOrder.status == "confirmed")) or 0
    if waiting:
        section.lines.append(f"Teslim bekleyen {waiting} onaylı sipariş var.")
    return section


def _finance_section(db: Session, company_id: uuid.UUID, start: date, today: date) -> Section:
    section = Section("Finans", "/panel/finans?gorunum=vadeler")
    previous = (start - timedelta(days=7), start - timedelta(days=1))
    collected = db.execute(
        select(FinancialRecord.currency, func.sum(FinancialPayment.amount))
        .join(FinancialRecord, FinancialRecord.id == FinancialPayment.record_id)
        .where(
            FinancialRecord.company_id == company_id,
            FinancialRecord.kind == "income",
            FinancialRecord.status != "cancelled",
            FinancialPayment.paid_on.between(*previous),
        )
        .group_by(FinancialRecord.currency)
    ).all()
    if any(amount for _, amount in collected):
        section.lines.append(f"Geçen hafta tahsilat: {_amounts(list(collected))}.")
    remaining = FinancialRecord.amount - FinancialRecord.paid_amount
    open_scope = (FinancialRecord.company_id == company_id, FinancialRecord.status.in_(OPEN_STATUSES))
    overdue = db.execute(
        select(FinancialRecord.currency, func.count(), func.sum(remaining))
        .where(*open_scope, FinancialRecord.kind == "income", FinancialRecord.due_date < today)
        .group_by(FinancialRecord.currency)
    ).all()
    if overdue:
        section.lines.append(f"Vadesi geçen {sum(int(row[1]) for row in overdue)} alacak: {_amounts([(row[0], row[2]) for row in overdue])}.")
    payable = db.execute(
        select(FinancialRecord.currency, func.count(), func.sum(remaining))
        .where(*open_scope, FinancialRecord.kind == "expense", FinancialRecord.due_date.between(today, today + timedelta(days=6)))
        .group_by(FinancialRecord.currency)
    ).all()
    if payable:
        section.lines.append(f"Bu hafta ödenecek {sum(int(row[1]) for row in payable)} borç: {_amounts([(row[0], row[2]) for row in payable])}.")
    return section


def _stock_section(db: Session, company_id: uuid.UUID) -> Section:
    section = Section("Stok", "/panel/stok?kritik=1")
    scope = (Product.company_id == company_id, Product.deleted_at.is_(None))
    critical = list(db.scalars(select(Product).where(*scope, CRITICAL_FILTER).order_by(Product.stock_quantity, Product.name)))
    low = [row for row in db.scalars(select(Product).where(*scope, LOW_FILTER).order_by(Product.stock_quantity, Product.name)) if row not in critical]
    if critical:
        names = ", ".join(f"{row.name} ({quantity_label(row.stock_quantity)} {row.unit}, kritik {quantity_label(critical_level(row) or Decimal(0))})" for row in critical[:LIST_LIMIT])
        section.lines.append(f"Kritik seviyede {len(critical)} ürün: {names}.")
    if low:
        names = ", ".join(f"{row.name} ({quantity_label(row.stock_quantity)}/{quantity_label(row.min_stock)} {row.unit})" for row in low[:LIST_LIMIT])
        section.lines.append(f"Minimumun altında {len(low)} ürün: {names}.")
    return section


def _project_section(db: Session, company_id: uuid.UUID, today: date) -> Section:
    section = Section("Projeler", "/panel/projeler")
    late = list(
        db.scalars(
            select(Project)
            .where(Project.company_id == company_id, Project.deleted_at.is_(None), Project.status != "completed", Project.due_date < today)
            .order_by(Project.due_date)
        )
    )
    if late:
        section.lines.append(f"Teslim tarihi geçen {len(late)} proje: " + ", ".join(f"{row.name} ({_day(row.due_date)})" for row in late[:LIST_LIMIT]) + ".")  # type: ignore[arg-type]
    return section


def build_sections(db: Session, member: Member, start: date, today: date) -> list[Section]:
    enabled = visible_keys(db, member)
    sections: list[Section] = []
    if "tasks" in enabled:
        sections.append(_task_section(db, member, today))
    if member.role in MANAGERS:
        company_id = member.company.id
        if "sales" in enabled:
            sections.append(_sales_section(db, company_id, start))
        if "finance" in enabled:
            sections.append(_finance_section(db, company_id, start, today))
        if "inventory" in enabled:
            sections.append(_stock_section(db, company_id))
        if "projects" in enabled:
            sections.append(_project_section(db, company_id, today))
    return [section for section in sections if section.lines]


def send_digests(db: Session, company: Company, members: list[tuple[User, str]], now: datetime | None = None) -> int:
    """Queues this week's digest for every member who wants it. Adds to the session; the caller commits."""
    if not mail.configured():
        return 0
    current = now or local_now(db, company)
    start = week_start(current)
    if start is None:
        return 0
    ref = f"digest:{start.isoformat()}"
    queued = 0
    for user, role in members:
        if user.status != "active" or not wants_email(db, company.id, user.id, "digest"):
            continue
        if db.scalar(select(EmailMessage.id).where(EmailMessage.user_id == user.id, EmailMessage.ref == ref, EmailMessage.company_id == company.id)):
            continue
        sections = build_sections(db, Member(user=user, company=company, role=role), start, current.date())
        if not sections:
            continue
        period = f"{_day(start)} haftası"
        draft = mail.digest_mail(company.name, user.first_name, period, [(section.title, section.lines, section.link) for section in sections])
        mail.enqueue(db, kind="digest", to=user.email, draft=draft, company_id=company.id, user_id=user.id, ref=ref)
        queued += 1
    return queued
