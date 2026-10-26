from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_csrf, require_module
from app.core.database import get_db
from app.modules.production import recipes
from app.modules.production.schemas import (
    CancelInput,
    ProductionDetail,
    ProductionInput,
    ProductionPage,
    ProductionSort,
    ProductionStatus,
    ProductionSummary,
    RecipeInput,
    RecipeOut,
    RecipeSummary,
)
from app.modules.production.service import (
    ProductionError,
    cancel_order,
    complete_order,
    create_order,
    get_order,
    list_orders,
    production_summary,
    start_order,
    update_order,
)
from app.services.auth import Member

router = APIRouter(prefix="/production")
production_member = require_module("production")


def _raise(error: ProductionError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.detail)


@router.get("/summary", response_model=ProductionSummary)
def read_summary(db: Session = Depends(get_db), member: Member = Depends(production_member)) -> ProductionSummary:
    return production_summary(db, member)


@router.get("/recipes", response_model=list[RecipeSummary])
def read_recipes(db: Session = Depends(get_db), member: Member = Depends(production_member)) -> list[RecipeSummary]:
    return recipes.list_recipes(db, member)


@router.get("/recipes/{product_id}", response_model=RecipeOut)
def read_recipe(product_id: UUID, db: Session = Depends(get_db), member: Member = Depends(production_member)) -> RecipeOut:
    try:
        return recipes.read_recipe(db, member, product_id)
    except recipes.RecipeError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None


@router.put("/recipes/{product_id}", response_model=RecipeOut)
def change_recipe(
    product_id: UUID,
    payload: RecipeInput,
    db: Session = Depends(get_db),
    member: Member = Depends(production_member),
    _: None = Depends(require_csrf),
) -> RecipeOut:
    try:
        return recipes.save_recipe(db, member, product_id, payload)
    except recipes.RecipeError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None


@router.get("/orders", response_model=ProductionPage)
def read_orders(
    q: str | None = Query(default=None, max_length=120),
    status: ProductionStatus | None = None,
    sort: ProductionSort = "-created_at",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    member: Member = Depends(production_member),
) -> ProductionPage:
    return list_orders(db, member, query=q, status=status, sort=sort, page=page, page_size=page_size)


@router.post("/orders", response_model=ProductionDetail, status_code=201)
def add_order(
    payload: ProductionInput,
    db: Session = Depends(get_db),
    member: Member = Depends(production_member),
    _: None = Depends(require_csrf),
) -> ProductionDetail:
    try:
        return create_order(db, member, payload)
    except ProductionError as error:
        _raise(error)


@router.get("/orders/{order_id}", response_model=ProductionDetail)
def read_order(order_id: UUID, db: Session = Depends(get_db), member: Member = Depends(production_member)) -> ProductionDetail:
    try:
        return get_order(db, member, order_id)
    except ProductionError as error:
        _raise(error)


@router.put("/orders/{order_id}", response_model=ProductionDetail)
def change_order(
    order_id: UUID,
    payload: ProductionInput,
    db: Session = Depends(get_db),
    member: Member = Depends(production_member),
    _: None = Depends(require_csrf),
) -> ProductionDetail:
    try:
        return update_order(db, member, order_id, payload)
    except ProductionError as error:
        _raise(error)


@router.post("/orders/{order_id}/start", response_model=ProductionDetail)
def begin_order(
    order_id: UUID,
    db: Session = Depends(get_db),
    member: Member = Depends(production_member),
    _: None = Depends(require_csrf),
) -> ProductionDetail:
    try:
        return start_order(db, member, order_id)
    except ProductionError as error:
        _raise(error)


@router.post("/orders/{order_id}/complete", response_model=ProductionDetail)
def finish_order(
    order_id: UUID,
    db: Session = Depends(get_db),
    member: Member = Depends(production_member),
    _: None = Depends(require_csrf),
) -> ProductionDetail:
    try:
        return complete_order(db, member, order_id)
    except ProductionError as error:
        _raise(error)


@router.post("/orders/{order_id}/cancel", response_model=ProductionDetail)
def void_order(
    order_id: UUID,
    payload: CancelInput,
    db: Session = Depends(get_db),
    member: Member = Depends(production_member),
    _: None = Depends(require_csrf),
) -> ProductionDetail:
    try:
        return cancel_order(db, member, order_id, payload)
    except ProductionError as error:
        _raise(error)
