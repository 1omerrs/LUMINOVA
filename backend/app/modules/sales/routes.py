from collections.abc import Callable
from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_csrf, require_module
from app.core.database import get_db
from app.modules.sales.rules import read_rules, save_rules
from app.modules.sales.schemas import (
    OrderDetail,
    OrderInput,
    OrderPage,
    OrderSort,
    OrderStatus,
    SalesRulesInput,
    SalesRulesOut,
    SalesSummary,
    TransitionInput,
)
from app.modules.sales.service import (
    SalesError,
    cancel_order,
    confirm_order,
    create_order,
    fulfil_order,
    get_order,
    list_orders,
    sales_summary,
    update_order,
)
from app.services.auth import Member

router = APIRouter(prefix="/sales")
sales_member = require_module("sales")


def _raise(error: SalesError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.detail)


@router.get("/summary", response_model=SalesSummary)
def read_summary(db: Session = Depends(get_db), member: Member = Depends(sales_member)) -> SalesSummary:
    return sales_summary(db, member)


@router.get("/rules", response_model=SalesRulesOut)
def read_sales_rules(db: Session = Depends(get_db), member: Member = Depends(sales_member)) -> SalesRulesOut:
    return read_rules(db, member)


@router.put("/rules", response_model=SalesRulesOut)
def change_sales_rules(
    payload: SalesRulesInput,
    db: Session = Depends(get_db),
    member: Member = Depends(sales_member),
    _: None = Depends(require_csrf),
) -> SalesRulesOut:
    if member.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Satış kurallarını yalnızca şirket sahibi veya yönetici değiştirebilir.")
    try:
        return save_rules(db, member, payload)
    except SalesError as error:
        _raise(error)


@router.get("/orders", response_model=OrderPage)
def read_orders(
    q: str | None = Query(default=None, max_length=120),
    status: OrderStatus | None = None,
    sort: OrderSort = "-created_at",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    member: Member = Depends(sales_member),
) -> OrderPage:
    return list_orders(db, member, query=q, status=status, sort=sort, page=page, page_size=page_size)


@router.post("/orders", response_model=OrderDetail, status_code=201)
def add_order(
    payload: OrderInput,
    db: Session = Depends(get_db),
    member: Member = Depends(sales_member),
    _: None = Depends(require_csrf),
) -> OrderDetail:
    try:
        return create_order(db, member, payload)
    except SalesError as error:
        _raise(error)


@router.get("/orders/{order_id}", response_model=OrderDetail)
def read_order(order_id: UUID, db: Session = Depends(get_db), member: Member = Depends(sales_member)) -> OrderDetail:
    try:
        return get_order(db, member, order_id)
    except SalesError as error:
        _raise(error)


@router.put("/orders/{order_id}", response_model=OrderDetail)
def change_order(
    order_id: UUID,
    payload: OrderInput,
    db: Session = Depends(get_db),
    member: Member = Depends(sales_member),
    _: None = Depends(require_csrf),
) -> OrderDetail:
    try:
        return update_order(db, member, order_id, payload)
    except SalesError as error:
        _raise(error)


def _transition_route(action: Callable[[Session, Member, UUID, str | None], OrderDetail]):
    def handler(
        order_id: UUID,
        payload: TransitionInput | None = None,
        db: Session = Depends(get_db),
        member: Member = Depends(sales_member),
        _: None = Depends(require_csrf),
    ) -> OrderDetail:
        try:
            return action(db, member, order_id, payload.note if payload else None)
        except SalesError as error:
            _raise(error)

    return handler


router.add_api_route("/orders/{order_id}/confirm", _transition_route(confirm_order), methods=["POST"], response_model=OrderDetail)
router.add_api_route("/orders/{order_id}/fulfil", _transition_route(fulfil_order), methods=["POST"], response_model=OrderDetail)
router.add_api_route("/orders/{order_id}/cancel", _transition_route(cancel_order), methods=["POST"], response_model=OrderDetail)
