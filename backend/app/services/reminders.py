"""Due-date reminders written when a member opens their notification feed.

There is no background scheduler; dedupe keys make repeated calls safe.
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.finance.models import OPEN_STATUSES, FinancialRecord
from app.modules.tasks.models import Task
from app.modules.tasks.service import company_today
from app.services.auth import Member
from app.services.modules import visible_keys
from app.services.notifications import notify

LIMIT = 10
FINANCE_DAYS = 3


def generate_reminders(db: Session, member: Member) -> None:
    if member.company.setup_completed_at is None:
        return
    enabled = visible_keys(db, member)
    today = company_today(db, member)
    written = 0

    if "tasks" in enabled:
        tasks = db.scalars(
            select(Task)
            .where(
                Task.company_id == member.company.id,
                Task.assignee_user_id == member.user.id,
                Task.deleted_at.is_(None),
                Task.source_key.is_(None),
                Task.status != "done",
                Task.due_date.is_not(None),
                Task.due_date <= today + timedelta(days=1),
            )
            .order_by(Task.due_date)
            .limit(LIMIT)
        ).all()
        for task in tasks:
            due = task.due_date
            if due is None:
                continue
            if due < today:
                title, key = f"Görev gecikti: {task.title}"[:160], f"reminder.task_late:{task.id.hex}:{due.isoformat()}"
            elif due == today:
                title, key = f"Görev bugün teslim: {task.title}"[:160], f"reminder.task_today:{task.id.hex}:{due.isoformat()}"
            else:
                title, key = f"Görev yarın teslim: {task.title}"[:160], f"reminder.task_soon:{task.id.hex}:{due.isoformat()}"
            notify(db, member, category="tasks", title=title, link="/panel/gorevler?sorumlu=me", dedupe_key=key)
            written += 1

    if "finance" in enabled and member.role in {"owner", "admin"} and written < LIMIT:
        records = db.scalars(
            select(FinancialRecord)
            .where(
                FinancialRecord.company_id == member.company.id,
                FinancialRecord.status.in_(OPEN_STATUSES),
                FinancialRecord.due_date.is_not(None),
                FinancialRecord.due_date <= today + timedelta(days=FINANCE_DAYS),
            )
            .order_by(FinancialRecord.due_date)
            .limit(LIMIT - written)
        ).all()
        for record in records:
            due = record.due_date
            if due is None:
                continue
            kind = "Tahsilat" if record.kind == "income" else "Ödeme"
            late = due < today
            notify(
                db,
                member,
                category="finance",
                title=(f"{kind} vadesi geçti: {record.description}" if late else f"{kind} vadesi yaklaşıyor: {record.description}")[:160],
                body=f"Vade {due.day:02d}.{due.month:02d}.{due.year}.",
                link="/panel/finans",
                dedupe_key=f"reminder.finance_{'late' if late else 'soon'}:{record.id.hex}:{due.isoformat()}",
            )
    db.commit()
