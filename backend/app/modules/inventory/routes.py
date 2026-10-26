from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import require_csrf, require_module
from app.core.database import get_db
from app.modules.inventory.schemas import (
    InventorySummary,
    MovementInput,
    MovementPage,
    MovementResult,
    ProductCreate,
    ProductInput,
    ProductItem,
    ProductPage,
    ProductSort,
    ReorderSuggestion,
)
from app.modules.inventory.service import (
    InventoryError,
    reorder_suggestions,
    create_product,
    delete_product,
    get_product,
    inventory_summary,
    list_movements,
    list_products,
    record_movement,
    update_product,
)
from app.services.auth import Member

router = APIRouter(prefix="/inventory")
inventory_member = require_module("inventory")


def _raise(error: InventoryError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.detail)


@router.get("/summary", response_model=InventorySummary)
def read_summary(db: Session = Depends(get_db), member: Member = Depends(inventory_member)) -> InventorySummary:
    return inventory_summary(db, member)


@router.get("/reorder", response_model=list[ReorderSuggestion])
def read_reorder(db: Session = Depends(get_db), member: Member = Depends(inventory_member)) -> list[ReorderSuggestion]:
    return reorder_suggestions(db, member)


@router.get("/products", response_model=ProductPage)
def read_products(
    q: str | None = Query(default=None, max_length=120),
    sort: ProductSort = "-created_at",
    low: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    member: Member = Depends(inventory_member),
) -> ProductPage:
    return list_products(db, member, query=q, sort=sort, low_only=low, page=page, page_size=page_size)


@router.post("/products", response_model=ProductItem, status_code=201)
def add_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    member: Member = Depends(inventory_member),
    _: None = Depends(require_csrf),
) -> ProductItem:
    try:
        return create_product(db, member, payload)
    except InventoryError as error:
        _raise(error)


@router.get("/products/{product_id}", response_model=ProductItem)
def read_product(product_id: UUID, db: Session = Depends(get_db), member: Member = Depends(inventory_member)) -> ProductItem:
    try:
        return get_product(db, member, product_id)
    except InventoryError as error:
        _raise(error)


@router.put("/products/{product_id}", response_model=ProductItem)
def change_product(
    product_id: UUID,
    payload: ProductInput,
    db: Session = Depends(get_db),
    member: Member = Depends(inventory_member),
    _: None = Depends(require_csrf),
) -> ProductItem:
    try:
        return update_product(db, member, product_id, payload)
    except InventoryError as error:
        _raise(error)


@router.delete("/products/{product_id}", status_code=204)
def remove_product(
    product_id: UUID,
    db: Session = Depends(get_db),
    member: Member = Depends(inventory_member),
    _: None = Depends(require_csrf),
) -> Response:
    try:
        delete_product(db, member, product_id)
    except InventoryError as error:
        _raise(error)
    return Response(status_code=204)


@router.get("/products/{product_id}/movements", response_model=MovementPage)
def read_movements(
    product_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    member: Member = Depends(inventory_member),
) -> MovementPage:
    try:
        return list_movements(db, member, product_id, page=page, page_size=page_size)
    except InventoryError as error:
        _raise(error)


@router.post("/products/{product_id}/movements", response_model=MovementResult, status_code=201)
def add_movement(
    product_id: UUID,
    payload: MovementInput,
    db: Session = Depends(get_db),
    member: Member = Depends(inventory_member),
    _: None = Depends(require_csrf),
) -> MovementResult:
    try:
        product, movement = record_movement(db, member, product_id, payload)
    except InventoryError as error:
        _raise(error)
    return MovementResult(product=product, movement=movement)
