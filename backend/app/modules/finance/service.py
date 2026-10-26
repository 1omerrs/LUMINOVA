import calendar
import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, literal, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.identity import AuditLog, User
from app.modules.customers.models import Customer
from app.modules.finance.models import OPEN_STATUSES, FinancialPayment, FinancialRecord, FinancialRecordRevision
from app.modules.finance.schemas import (
    CancelInput,
    CurrencyTotals,
    FinanceSummary,
    PaymentInput,
    PaymentItem,
    RecordDetail,
    RecordInput,
    RecordItem,
    RecordKind,
    RecordPage,
    RecordSort,
    RecordStatus,
    Revision,
)
from app.modules.sales.models import SalesOrder
from app.modules.sales.service import order_code
from app.modules.tasks.service import company_today
from app.services.auth import Member
from app.services.automation import emit

CENT = Decimal("0.01")
CURRENCIES = ("TRY", "USD", "EUR")
DUPLICATE_ORDER = "Bu sipariş için zaten bir gelir kaydı var."
_TURKISH = "tr-TR-x-icu"
_TRACKED = ("kind", "category", "description", "counterparty", "customer_id", "amount", "currency", "record_date", "due_date", "status", "paid_on", "note")
_ORDER = {
    "-record_date": (FinancialRecord.record_date.desc(), FinancialRecord.created_at.desc()),
    "record_date": (FinancialRecord.record_date.asc(), FinancialRecord.created_at.asc()),
    "-amount": (FinancialRecord.amount.desc(), FinancialRecord.record_date.desc()),
    "due_date": (FinancialRecord.due_date.asc().nulls_last(), FinancialRecord.record_date.asc()),
}


class FinanceError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


def money(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def list_records(
    db: Session,
    member: Member,
    *,
    query: str | None,
    kind: RecordKind | None,
    status: RecordStatus | None,
    overdue: bool,
    date_from: date | None,
    date_to: date | None,
    order_id: uuid.UUID | None,
    sort: RecordSort,
    page: int,
    page_size: int,
    open_only: bool = False,
    due_to: date | None = None,
    customer_id: uuid.UUID | None = None,
) -> RecordPage:
    today = company_today(db, member)
    filters = [FinancialRecord.company_id == member.company.id]
    if kind is not None:
        filters.append(FinancialRecord.kind == kind)
    if status is not None:
        filters.append(FinancialRecord.status == status)
    if overdue:
        filters.extend([FinancialRecord.status.in_(OPEN_STATUSES), FinancialRecord.due_date < today])
    if open_only:
        filters.append(FinancialRecord.status.in_(OPEN_STATUSES))
    if due_to is not None:
        filters.append(FinancialRecord.due_date <= due_to)
    if customer_id is not None:
        filters.append(FinancialRecord.customer_id == customer_id)
    if date_from is not None:
        filters.append(FinancialRecord.record_date >= date_from)
    if date_to is not None:
        filters.append(FinancialRecord.record_date <= date_to)
    if order_id is not None:
        filters.append(FinancialRecord.order_id == order_id)
    term = (query or "").strip()
    if term:
        pattern = func.lower(literal(f"%{term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')}%").collate(_TURKISH))
        filters.append(
            or_(
                func.lower(FinancialRecord.description.collate(_TURKISH)).like(pattern, escape="\\"),
                func.lower(FinancialRecord.counterparty.collate(_TURKISH)).like(pattern, escape="\\"),
                func.lower(Customer.name.collate(_TURKISH)).like(pattern, escape="\\"),
            )
        )
    base = (
        select(FinancialRecord, Customer.name, SalesOrder.number)
        .outerjoin(Customer, Customer.id == FinancialRecord.customer_id)
        .outerjoin(SalesOrder, SalesOrder.id == FinancialRecord.order_id)
        .where(*filters)
    )
    total = db.scalar(
        select(func.count()).select_from(FinancialRecord).outerjoin(Customer, Customer.id == FinancialRecord.customer_id).where(*filters)
    ) or 0
    rows = db.execute(base.order_by(*_ORDER[sort], FinancialRecord.id).offset((page - 1) * page_size).limit(page_size)).all()
    return RecordPage(
        items=[_item(record, customer, number, today) for record, customer, number in rows],
        total=int(total),
        page=page,
        page_size=page_size,
        today=today,
    )


def finance_summary(db: Session, member: Member, *, date_from: date | None, date_to: date | None) -> FinanceSummary:
    today = company_today(db, member)
    start = date_from or today.replace(day=1)
    end = date_to or today.replace(day=calendar.monthrange(today.year, today.month)[1])
    if end < start:
        raise FinanceError(422, "Dönem bitişi başlangıçtan önce olamaz.")
    scope = (FinancialRecord.company_id == member.company.id, FinancialRecord.status != "cancelled")
    period = db.execute(
        select(FinancialRecord.currency, FinancialRecord.kind, func.sum(FinancialRecord.amount))
        .where(*scope, FinancialRecord.record_date.between(start, end))
        .group_by(FinancialRecord.currency, FinancialRecord.kind)
    ).all()
    open_rows = db.execute(
        select(FinancialRecord.currency, FinancialRecord.kind, func.sum(FinancialRecord.amount - FinancialRecord.paid_amount))
        .where(FinancialRecord.company_id == member.company.id, FinancialRecord.status.in_(OPEN_STATUSES))
        .group_by(FinancialRecord.currency, FinancialRecord.kind)
    ).all()
    sums: dict[tuple[str, str, str], Decimal] = {}
    for currency, kind, amount in period:
        sums[(currency, kind, "period")] = Decimal(amount)
    for currency, kind, amount in open_rows:
        sums[(currency, kind, "open")] = Decimal(amount)
    used = {key[0] for key in sums}
    totals = []
    for currency in CURRENCIES:
        if currency != "TRY" and currency not in used:
            continue
        income = sums.get((currency, "income", "period"), Decimal(0))
        expense = sums.get((currency, "expense", "period"), Decimal(0))
        totals.append(
            CurrencyTotals(
                currency=currency,
                income=money(income),
                expense=money(expense),
                net=money(income - expense),
                receivable=money(sums.get((currency, "income", "open"), Decimal(0))),
                payable=money(sums.get((currency, "expense", "open"), Decimal(0))),
            )
        )
    late = dict(
        db.execute(
            select(FinancialRecord.kind, func.count())
            .where(FinancialRecord.company_id == member.company.id, FinancialRecord.status.in_(OPEN_STATUSES), FinancialRecord.due_date < today)
            .group_by(FinancialRecord.kind)
        ).all()
    )
    return FinanceSummary(
        today=today,
        period_from=start,
        period_to=end,
        totals=totals,
        overdue_receivables=int(late.get("income", 0)),
        overdue_payables=int(late.get("expense", 0)),
    )


def get_record(db: Session, member: Member, record_id: uuid.UUID) -> RecordDetail:
    return _detail(db, member, _owned(db, member, record_id))


def create_record(db: Session, member: Member, data: RecordInput) -> RecordDetail:
    record = add_record(db, member, data)
    _commit(db)
    return _detail(db, member, record)


def cancel_for_order(db: Session, member: Member, order_id: uuid.UUID, reason: str) -> tuple[int, int]:
    """Cancel the pending income records of a cancelled order; returns (cancelled, left_paid). No commit."""
    records = db.scalars(
        select(FinancialRecord)
        .where(FinancialRecord.company_id == member.company.id, FinancialRecord.order_id == order_id, FinancialRecord.status != "cancelled")
        .with_for_update()
    ).all()
    cancelled = paid = 0
    for record in records:
        if record.paid_amount > 0:
            paid += 1
            continue
        record.status = "cancelled"
        record.cancel_reason = reason[:300]
        record.updated_at = datetime.now(UTC)
        _revise(db, member, record, "cancelled", {"status": {"from": "pending", "to": "cancelled"}}, reason[:300])
        db.add(_audit(member, "finance.record_cancelled", record, {"auto": True}))
        cancelled += 1
    return cancelled, paid


def add_record(db: Session, member: Member, data: RecordInput) -> FinancialRecord:
    """Validate and add a record to the session without committing."""
    _require_customer(db, member, data.customer_id)
    if data.order_id is not None:
        _require_order(db, member, data)
    today = company_today(db, member)
    record = FinancialRecord(
        id=uuid.uuid4(),
        company_id=member.company.id,
        kind=data.kind,
        category=data.category,
        description=data.description,
        counterparty=data.counterparty,
        customer_id=data.customer_id,
        order_id=data.order_id,
        amount=data.amount,
        currency=data.currency,
        record_date=data.record_date,
        due_date=data.due_date,
        status="pending",
        note=data.note,
        created_by=member.user.id,
    )
    db.add(record)
    db.flush()
    if data.status == "paid":
        _add_payment(db, member, record, data.amount, data.paid_on or today, "transfer", None)
        _sync(db, record)
    _revise(db, member, record, "created", {})
    db.add(_audit(member, "finance.record_created", record, {"kind": record.kind, "order": bool(record.order_id)}))
    emit(
        db,
        member,
        "finance.record_created",
        {
            "id": str(record.id),
            "kind": record.kind,
            "category": record.category,
            "description": record.description,
            "amount": f"{record.amount:.2f}",
            "currency": record.currency,
            "status": record.status,
            "record_date": record.record_date.isoformat(),
            "due_date": record.due_date.isoformat() if record.due_date else None,
            "order_id": str(record.order_id) if record.order_id else None,
        },
    )
    return record


def update_record(db: Session, member: Member, record_id: uuid.UUID, data: RecordInput) -> RecordDetail:
    record = _owned(db, member, record_id, lock=True)
    if record.status == "cancelled":
        raise FinanceError(409, "İptal edilen kayıt düzenlenemez.")
    if record.order_id is not None and data.kind != "income":
        raise FinanceError(422, "Siparişe bağlı kayıt gider olamaz.")
    if data.customer_id != record.customer_id:
        _require_customer(db, member, data.customer_id)
    if data.amount < record.paid_amount:
        raise FinanceError(422, f"Tutar, alınan ödemelerden ({money(record.paid_amount)} {record.currency}) az olamaz. Önce ödemeyi kaldırın.")
    today = company_today(db, member)
    before = {field: getattr(record, field) for field in (*_TRACKED, "paid_amount")}
    for field in _TRACKED:
        if field not in {"status", "paid_on"}:
            setattr(record, field, getattr(data, field))
    payments = list(db.scalars(select(FinancialPayment).where(FinancialPayment.record_id == record.id)))
    if data.status == "paid" and record.paid_amount < record.amount:
        _add_payment(db, member, record, record.amount - record.paid_amount, data.paid_on or today, "transfer", None)
    elif data.status == "paid" and data.paid_on and len(payments) == 1 and payments[0].paid_on != data.paid_on:
        payments[0].paid_on = data.paid_on
    elif data.status == "pending" and before["status"] == "paid":
        for payment in payments:
            db.delete(payment)
    _sync(db, record)
    changes = {
        field: {"from": _text(old), "to": _text(getattr(record, field))} for field, old in before.items() if getattr(record, field) != old
    }
    if not changes:
        return _detail(db, member, record)
    record.updated_at = datetime.now(UTC)
    _revise(db, member, record, "updated", changes)
    db.add(_audit(member, "finance.record_updated", record, {"fields": sorted(changes)}))
    db.commit()
    return _detail(db, member, record)


def _add_payment(db: Session, member: Member, record: FinancialRecord, amount: Decimal, paid_on: date, method: str, note: str | None) -> FinancialPayment:
    payment = FinancialPayment(company_id=member.company.id, record_id=record.id, amount=amount, paid_on=paid_on, method=method, note=note, created_by=member.user.id)
    db.add(payment)
    return payment


def _sync(db: Session, record: FinancialRecord) -> None:
    """Derive paid amount, status and paid date from the record's payments."""
    db.flush()
    paid, last = db.execute(
        select(func.coalesce(func.sum(FinancialPayment.amount), 0), func.max(FinancialPayment.paid_on)).where(FinancialPayment.record_id == record.id)
    ).one()
    record.paid_amount = Decimal(paid)
    if record.status == "cancelled":
        return
    record.status = "paid" if record.paid_amount >= record.amount else "partial" if record.paid_amount > 0 else "pending"
    record.paid_on = last if record.status == "paid" else None


def record_payment(db: Session, member: Member, record_id: uuid.UUID, data: PaymentInput) -> RecordDetail:
    record = _owned(db, member, record_id, lock=True)
    if record.status == "cancelled":
        raise FinanceError(409, "İptal edilen kayda ödeme eklenemez.")
    remaining = record.amount - record.paid_amount
    if remaining <= 0:
        raise FinanceError(409, "Bu kaydın tamamı zaten ödendi.")
    if data.amount > remaining:
        raise FinanceError(422, f"Kalan tutar {money(remaining)} {record.currency}; daha fazlası girilemez.")
    if data.paid_on > company_today(db, member):
        raise FinanceError(422, "Ödeme tarihi ileri bir gün olamaz.")
    before = record.paid_amount
    _add_payment(db, member, record, data.amount, data.paid_on, data.method, data.note)
    _sync(db, record)
    record.updated_at = datetime.now(UTC)
    _revise(db, member, record, "payment_added", {"paid_amount": {"from": money(before), "to": money(record.paid_amount)}})
    db.add(_audit(member, "finance.payment_added", record, {"amount": money(data.amount), "currency": record.currency, "status": record.status}))
    db.commit()
    return _detail(db, member, record)


def remove_payment(db: Session, member: Member, record_id: uuid.UUID, payment_id: uuid.UUID) -> RecordDetail:
    record = _owned(db, member, record_id, lock=True)
    if record.status == "cancelled":
        raise FinanceError(409, "İptal edilen kaydın ödemeleri değiştirilemez.")
    payment = db.scalar(select(FinancialPayment).where(FinancialPayment.id == payment_id, FinancialPayment.record_id == record.id))
    if payment is None:
        raise FinanceError(404, "Ödeme bulunamadı.")
    before = record.paid_amount
    amount = payment.amount
    db.delete(payment)
    _sync(db, record)
    record.updated_at = datetime.now(UTC)
    _revise(db, member, record, "payment_removed", {"paid_amount": {"from": money(before), "to": money(record.paid_amount)}})
    db.add(_audit(member, "finance.payment_removed", record, {"amount": money(amount), "currency": record.currency}))
    db.commit()
    return _detail(db, member, record)


def cancel_record(db: Session, member: Member, record_id: uuid.UUID, data: CancelInput) -> RecordDetail:
    record = _owned(db, member, record_id, lock=True)
    if record.status == "cancelled":
        raise FinanceError(409, "Bu kayıt zaten iptal edildi.")
    changes = {"status": {"from": record.status, "to": "cancelled"}}
    if record.paid_on is not None:
        changes["paid_on"] = {"from": _text(record.paid_on), "to": None}
    record.status = "cancelled"
    record.paid_on = None
    record.cancel_reason = data.reason
    record.updated_at = datetime.now(UTC)
    _revise(db, member, record, "cancelled", changes, data.reason)
    db.add(_audit(member, "finance.record_cancelled", record, {}))
    db.commit()
    return _detail(db, member, record)


def _require_customer(db: Session, member: Member, customer_id: uuid.UUID | None) -> None:
    if customer_id is None:
        return
    exists = db.scalar(
        select(Customer.id).where(Customer.id == customer_id, Customer.company_id == member.company.id, Customer.deleted_at.is_(None))
    )
    if exists is None:
        raise FinanceError(422, "Seçilen müşteri bulunamadı.")


def _require_order(db: Session, member: Member, data: RecordInput) -> None:
    if data.kind != "income":
        raise FinanceError(422, "Siparişe bağlı kayıt gider olamaz.")
    order = db.scalar(select(SalesOrder).where(SalesOrder.id == data.order_id, SalesOrder.company_id == member.company.id).with_for_update())
    if order is None:
        raise FinanceError(422, "Seçilen sipariş bulunamadı.")
    if order.status not in {"confirmed", "fulfilled"}:
        raise FinanceError(409, "Gelir kaydı yalnızca onaylanmış veya teslim edilmiş siparişten oluşturulur.")
    taken = db.scalar(
        select(FinancialRecord.id).where(
            FinancialRecord.company_id == member.company.id,
            FinancialRecord.order_id == order.id,
            FinancialRecord.status != "cancelled",
        )
    )
    if taken is not None:
        raise FinanceError(409, DUPLICATE_ORDER)


def _revise(db: Session, member: Member, record: FinancialRecord, action: str, changes: dict[str, dict[str, str | None]], reason: str | None = None) -> None:
    last = db.scalar(select(func.max(FinancialRecordRevision.revision)).where(FinancialRecordRevision.record_id == record.id)) or 0
    db.add(
        FinancialRecordRevision(
            company_id=member.company.id,
            record_id=record.id,
            revision=int(last) + 1,
            action=action,
            changes=changes,
            reason=reason,
            actor_user_id=member.user.id,
        )
    )


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if "uq_financial_records_order_id" in str(error.orig):
            raise FinanceError(409, DUPLICATE_ORDER) from None
        raise


def _owned(db: Session, member: Member, record_id: uuid.UUID, *, lock: bool = False) -> FinancialRecord:
    statement = select(FinancialRecord).where(FinancialRecord.id == record_id, FinancialRecord.company_id == member.company.id)
    if lock:
        statement = statement.with_for_update()
    record = db.scalar(statement)
    if record is None:
        raise FinanceError(404, "Kayıt bulunamadı.")
    return record


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return money(value)
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _audit(member: Member, action: str, record: FinancialRecord, summary: dict[str, object]) -> AuditLog:
    return AuditLog(
        company_id=member.company.id,
        actor_user_id=member.user.id,
        action=action,
        entity_type="financial_record",
        entity_id=str(record.id),
        summary=summary,
        source="api",
    )


def _detail(db: Session, member: Member, record: FinancialRecord) -> RecordDetail:
    db.refresh(record)
    today = company_today(db, member)
    customer = db.scalar(select(Customer.name).where(Customer.id == record.customer_id)) if record.customer_id else None
    number = db.scalar(select(SalesOrder.number).where(SalesOrder.id == record.order_id)) if record.order_id else None
    revisions = db.execute(
        select(FinancialRecordRevision, User.first_name, User.last_name)
        .outerjoin(User, User.id == FinancialRecordRevision.actor_user_id)
        .where(FinancialRecordRevision.record_id == record.id)
        .order_by(FinancialRecordRevision.revision)
    ).all()
    payments = db.execute(
        select(FinancialPayment, User.first_name, User.last_name)
        .outerjoin(User, User.id == FinancialPayment.created_by)
        .where(FinancialPayment.record_id == record.id)
        .order_by(FinancialPayment.paid_on, FinancialPayment.created_at)
    ).all()
    return RecordDetail(
        **_item(record, customer, number, today).model_dump(),
        payments=[
            PaymentItem(
                id=row.id,
                amount=money(row.amount),
                paid_on=row.paid_on,
                method=row.method,  # type: ignore[arg-type]
                note=row.note,
                actor=f"{first} {last}" if first else None,
                created_at=row.created_at,
            )
            for row, first, last in payments
        ],
        revisions=[
            Revision(
                revision=row.revision,
                action=row.action,
                changes=row.changes,
                reason=row.reason,
                actor=f"{first} {last}" if first else None,
                created_at=row.created_at,
            )
            for row, first, last in revisions
        ],
    )


def _item(record: FinancialRecord, customer: str | None, order_number: int | None, today: date) -> RecordItem:
    return RecordItem(
        id=record.id,
        kind=record.kind,
        category=record.category,
        description=record.description,
        counterparty=record.counterparty,
        customer_id=record.customer_id,
        customer_name=customer,
        order_id=record.order_id,
        order_code=order_code(order_number) if order_number else None,
        amount=money(record.amount),
        paid_amount=money(record.paid_amount),
        remaining=money(record.amount - record.paid_amount) if record.status in OPEN_STATUSES else money(Decimal(0)),
        currency=record.currency,
        record_date=record.record_date,
        due_date=record.due_date,
        status=record.status,
        paid_on=record.paid_on,
        overdue=record.status in OPEN_STATUSES and record.due_date is not None and record.due_date < today,
        note=record.note,
        cancel_reason=record.cancel_reason,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
