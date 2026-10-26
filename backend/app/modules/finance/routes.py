from datetime import date
from typing import Literal, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_csrf, require_module
from app.core.database import get_db
from app.modules.finance.models import EXPENSE_CATEGORIES, INCOME_CATEGORIES
from app.modules.finance.reports import balances, cashflow, save_opening
from app.modules.finance.schemas import (
    Balance,
    BalanceInput,
    CancelInput,
    Cashflow,
    Categories,
    FinanceSummary,
    PaymentInput,
    RecordDetail,
    RecordInput,
    RecordKind,
    RecordPage,
    RecordSort,
    RecordStatus,
)
from app.modules.finance.service import (
    FinanceError,
    cancel_record,
    create_record,
    finance_summary,
    get_record,
    list_records,
    record_payment,
    remove_payment,
    update_record,
)
from app.services.auth import Member

router = APIRouter(prefix="/finance")
finance_member = require_module("finance")


def _raise(error: FinanceError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.detail)


@router.get("/categories", response_model=Categories)
def read_categories(_: Member = Depends(finance_member)) -> Categories:
    return Categories(income=list(INCOME_CATEGORIES), expense=list(EXPENSE_CATEGORIES))


@router.get("/summary", response_model=FinanceSummary)
def read_summary(
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    member: Member = Depends(finance_member),
) -> FinanceSummary:
    try:
        return finance_summary(db, member, date_from=date_from, date_to=date_to)
    except FinanceError as error:
        _raise(error)


@router.get("/records", response_model=RecordPage)
def read_records(
    q: str | None = Query(default=None, max_length=120),
    kind: RecordKind | None = None,
    status: RecordStatus | None = None,
    overdue: bool = False,
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    order_id: UUID | None = None,
    customer_id: UUID | None = None,
    open_only: bool = Query(default=False, alias="open"),
    due_to: date | None = None,
    sort: RecordSort = "-record_date",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    member: Member = Depends(finance_member),
) -> RecordPage:
    return list_records(
        db,
        member,
        query=q,
        kind=kind,
        status=status,
        overdue=overdue,
        date_from=date_from,
        date_to=date_to,
        order_id=order_id,
        sort=sort,
        page=page,
        page_size=page_size,
        open_only=open_only,
        due_to=due_to,
        customer_id=customer_id,
    )


@router.get("/balances", response_model=list[Balance])
def read_balances(db: Session = Depends(get_db), member: Member = Depends(finance_member)) -> list[Balance]:
    return balances(db, member)


@router.put("/opening-balance", response_model=Cashflow)
def change_opening_balance(
    payload: BalanceInput,
    db: Session = Depends(get_db),
    member: Member = Depends(finance_member),
    _: None = Depends(require_csrf),
) -> Cashflow:
    if member.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Açılış bakiyesini yalnızca şirket sahibi veya yönetici girebilir.")
    try:
        save_opening(db, member, payload)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    return cashflow(db, member, currency=payload.currency, weeks=8, past=4)


@router.get("/cashflow", response_model=Cashflow)
def read_cashflow(
    currency: Literal["TRY", "USD", "EUR"] = "TRY",
    weeks: int = Query(default=8, ge=1, le=26),
    past: int = Query(default=4, ge=0, le=12),
    db: Session = Depends(get_db),
    member: Member = Depends(finance_member),
) -> Cashflow:
    return cashflow(db, member, currency=currency, weeks=weeks, past=past)


@router.post("/records", response_model=RecordDetail, status_code=201)
def add_record(
    payload: RecordInput,
    db: Session = Depends(get_db),
    member: Member = Depends(finance_member),
    _: None = Depends(require_csrf),
) -> RecordDetail:
    try:
        return create_record(db, member, payload)
    except FinanceError as error:
        _raise(error)


@router.get("/records/{record_id}", response_model=RecordDetail)
def read_record(record_id: UUID, db: Session = Depends(get_db), member: Member = Depends(finance_member)) -> RecordDetail:
    try:
        return get_record(db, member, record_id)
    except FinanceError as error:
        _raise(error)


@router.put("/records/{record_id}", response_model=RecordDetail)
def change_record(
    record_id: UUID,
    payload: RecordInput,
    db: Session = Depends(get_db),
    member: Member = Depends(finance_member),
    _: None = Depends(require_csrf),
) -> RecordDetail:
    try:
        return update_record(db, member, record_id, payload)
    except FinanceError as error:
        _raise(error)


@router.post("/records/{record_id}/payments", response_model=RecordDetail, status_code=201)
def add_payment(
    record_id: UUID,
    payload: PaymentInput,
    db: Session = Depends(get_db),
    member: Member = Depends(finance_member),
    _: None = Depends(require_csrf),
) -> RecordDetail:
    try:
        return record_payment(db, member, record_id, payload)
    except FinanceError as error:
        _raise(error)


@router.delete("/records/{record_id}/payments/{payment_id}", response_model=RecordDetail)
def delete_payment(
    record_id: UUID,
    payment_id: UUID,
    db: Session = Depends(get_db),
    member: Member = Depends(finance_member),
    _: None = Depends(require_csrf),
) -> RecordDetail:
    try:
        return remove_payment(db, member, record_id, payment_id)
    except FinanceError as error:
        _raise(error)


@router.post("/records/{record_id}/cancel", response_model=RecordDetail)
def void_record(
    record_id: UUID,
    payload: CancelInput,
    db: Session = Depends(get_db),
    member: Member = Depends(finance_member),
    _: None = Depends(require_csrf),
) -> RecordDetail:
    try:
        return cancel_record(db, member, record_id, payload)
    except FinanceError as error:
        _raise(error)
