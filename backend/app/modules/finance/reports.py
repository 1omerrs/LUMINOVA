"""Customer balances and the weekly cash-flow view.

Open amounts are always `amount - paid_amount` of pending or partially paid records.
Expected money is placed in the week of its due date (record date when there is none);
anything due before today is reported separately as overdue.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.customers.models import Customer
from app.models.identity import AuditLog
from app.modules.finance.models import OPEN_STATUSES, CashBalance, FinancialPayment, FinancialRecord
from app.modules.finance.schemas import Balance, BalanceInput, Cashflow, CashflowWeek
from app.modules.finance.service import money
from app.modules.tasks.service import company_today
from app.services.auth import Member

ZERO = Decimal(0)


def balances(db: Session, member: Member) -> list[Balance]:
    today = company_today(db, member)
    rows = db.execute(
        select(FinancialRecord, Customer.name)
        .outerjoin(Customer, Customer.id == FinancialRecord.customer_id)
        .where(FinancialRecord.company_id == member.company.id, FinancialRecord.kind == "income", FinancialRecord.status.in_(OPEN_STATUSES))
    ).all()
    groups: dict[tuple[object, str, str], dict[str, object]] = {}
    for record, customer in rows:
        name = customer or record.counterparty or "Müşterisi belirtilmemiş"
        key = (record.customer_id or name, name, record.currency)
        group = groups.setdefault(key, {"open": ZERO, "late": ZERO, "count": 0, "oldest": None, "ids": []})
        remaining = record.amount - record.paid_amount
        group["open"] = group["open"] + remaining  # type: ignore[operator]
        if record.due_date is not None and record.due_date < today:
            group["late"] = group["late"] + remaining  # type: ignore[operator]
        group["count"] = int(group["count"]) + 1  # type: ignore[call-overload]
        due = record.due_date or record.record_date
        if group["oldest"] is None or due < group["oldest"]:  # type: ignore[operator]
            group["oldest"] = due
        group["ids"].append(record.id)  # type: ignore[union-attr]
    ids = [record_id for group in groups.values() for record_id in group["ids"]]  # type: ignore[attr-defined]
    last_paid = (
        dict(db.execute(select(FinancialPayment.record_id, func.max(FinancialPayment.paid_on)).where(FinancialPayment.record_id.in_(ids)).group_by(FinancialPayment.record_id)).all())
        if ids
        else {}
    )
    result = []
    for (owner, name, currency), group in groups.items():
        payments = [last_paid[record_id] for record_id in group["ids"] if record_id in last_paid]  # type: ignore[attr-defined]
        result.append(
            Balance(
                customer_id=owner if not isinstance(owner, str) else None,  # type: ignore[arg-type]
                name=name,
                currency=currency,  # type: ignore[arg-type]
                open_amount=money(group["open"]),  # type: ignore[arg-type]
                overdue_amount=money(group["late"]),  # type: ignore[arg-type]
                records=int(group["count"]),  # type: ignore[call-overload]
                oldest_due=group["oldest"],  # type: ignore[arg-type]
                last_payment=max(payments) if payments else None,
            )
        )
    result.sort(key=lambda item: (-Decimal(item.overdue_amount), -Decimal(item.open_amount)))
    return result


def save_opening(db: Session, member: Member, data: BalanceInput) -> None:
    if data.as_of > company_today(db, member):
        raise ValueError("Açılış bakiyesi tarihi ileri bir gün olamaz.")
    balance = db.get(CashBalance, (member.company.id, data.currency)) or CashBalance(company_id=member.company.id, currency=data.currency)
    balance.amount = data.amount
    balance.as_of = data.as_of
    balance.updated_by = member.user.id
    db.merge(balance)
    db.add(
        AuditLog(
            company_id=member.company.id,
            actor_user_id=member.user.id,
            action="finance.opening_balance_set",
            entity_type="cash_balance",
            entity_id=f"{member.company.id}:{data.currency}",
            summary={"currency": data.currency, "amount": money(data.amount), "as_of": data.as_of.isoformat()},
            source="api",
        )
    )
    db.commit()


def cashflow(db: Session, member: Member, *, currency: str, weeks: int, past: int) -> Cashflow:
    today = company_today(db, member)
    monday = today - timedelta(days=today.weekday())
    first = monday - timedelta(weeks=past)
    last = monday + timedelta(weeks=weeks) - timedelta(days=1)
    scope = (FinancialRecord.company_id == member.company.id, FinancialRecord.currency == currency)

    actual: dict[tuple[date, str], Decimal] = defaultdict(lambda: ZERO)
    for paid_on, kind, amount in db.execute(
        select(FinancialPayment.paid_on, FinancialRecord.kind, FinancialPayment.amount)
        .join(FinancialRecord, FinancialRecord.id == FinancialPayment.record_id)
        .where(*scope, FinancialRecord.status != "cancelled", FinancialPayment.paid_on.between(first, today))
    ).all():
        actual[(paid_on - timedelta(days=paid_on.weekday()), kind)] += Decimal(amount)

    expected: dict[tuple[date, str], Decimal] = defaultdict(lambda: ZERO)
    overdue = {"income": ZERO, "expense": ZERO}
    undated = {"income": ZERO, "expense": ZERO}
    for record in db.scalars(select(FinancialRecord).where(*scope, FinancialRecord.status.in_(OPEN_STATUSES))):
        remaining = record.amount - record.paid_amount
        if record.due_date is None:
            undated[record.kind] += remaining
            continue
        if record.due_date < today:
            overdue[record.kind] += remaining
        elif record.due_date <= last:
            expected[(record.due_date - timedelta(days=record.due_date.weekday()), record.kind)] += remaining

    rows = []
    for index in range(past + weeks):
        start = first + timedelta(weeks=index)
        rows.append(
            CashflowWeek(
                week_start=start,
                week_end=start + timedelta(days=6),
                actual_in=money(actual[(start, "income")]),
                actual_out=money(actual[(start, "expense")]),
                expected_in=money(expected[(start, "income")]),
                expected_out=money(expected[(start, "expense")]),
            )
        )
    opening = db.get(CashBalance, (member.company.id, currency))
    cash_now = None
    if opening is not None:
        moved = db.execute(
            select(FinancialRecord.kind, func.coalesce(func.sum(FinancialPayment.amount), 0))
            .join(FinancialRecord, FinancialRecord.id == FinancialPayment.record_id)
            .where(*scope, FinancialRecord.status != "cancelled", FinancialPayment.paid_on >= opening.as_of, FinancialPayment.paid_on <= today)
            .group_by(FinancialRecord.kind)
        ).all()
        flows = {kind: Decimal(amount) for kind, amount in moved}
        cash_now = opening.amount + flows.get("income", ZERO) - flows.get("expense", ZERO)
    return Cashflow(
        opening_amount=money(opening.amount) if opening else None,
        opening_as_of=opening.as_of if opening else None,
        cash_now=money(cash_now) if cash_now is not None else None,
        currency=currency,  # type: ignore[arg-type]
        today=today,
        overdue_in=money(overdue["income"]),
        overdue_out=money(overdue["expense"]),
        undated_in=money(undated["income"]),
        undated_out=money(undated["expense"]),
        weeks=rows,
    )
