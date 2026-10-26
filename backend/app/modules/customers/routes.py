from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import require_csrf, require_module
from app.core.database import get_db
from app.modules.customers import importer
from app.modules.customers.matching import find_matches
from app.modules.customers.overview import customer_overview
from app.modules.customers.schemas import (
    CustomerDetail,
    CustomerInput,
    CustomerItem,
    CustomerMatch,
    CustomerPage,
    CustomerSort,
    ImportFile,
    ImportPreview,
    ImportReport,
    ImportRequest,
)
from app.modules.customers.service import (
    CustomerError,
    create_customer,
    delete_customer,
    get_customer,
    list_customers,
    owned_customer,
    update_customer,
)
from app.services.auth import Member

router = APIRouter(prefix="/customers")
customers_member = require_module("customers")


def _raise(error: CustomerError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.detail)


@router.get("", response_model=CustomerPage)
def read_customers(
    q: str | None = Query(default=None, max_length=120),
    sort: CustomerSort = "-created_at",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    member: Member = Depends(customers_member),
) -> CustomerPage:
    return list_customers(db, member, query=q, sort=sort, page=page, page_size=page_size)


@router.post("", response_model=CustomerItem, status_code=201)
def add_customer(
    payload: CustomerInput,
    db: Session = Depends(get_db),
    member: Member = Depends(customers_member),
    _: None = Depends(require_csrf),
) -> CustomerItem:
    try:
        return create_customer(db, member, payload)
    except CustomerError as error:
        _raise(error)


@router.get("/matches", response_model=list[CustomerMatch])
def read_matches(
    name: str = Query(default="", max_length=160),
    email: str | None = Query(default=None, max_length=320),
    phone: str | None = Query(default=None, max_length=40),
    exclude: UUID | None = None,
    db: Session = Depends(get_db),
    member: Member = Depends(customers_member),
) -> list[CustomerMatch]:
    found = find_matches(db, member.company.id, name=name.strip(), email=(email or "").strip() or None, phone=(phone or "").strip() or None, exclude=exclude)
    return [CustomerMatch(id=item.id, name=item.name, email=item.email, phone=item.phone, reason=item.reason) for item in found]


@router.post("/import/preview", response_model=ImportPreview)
def import_preview(
    payload: ImportFile,
    _member: Member = Depends(customers_member),
    _: None = Depends(require_csrf),
) -> ImportPreview:
    try:
        return importer.preview(payload.filename, payload.content)
    except importer.ImportFailure as error:
        raise HTTPException(status_code=422, detail=error.detail) from None


@router.post("/import", response_model=ImportReport)
def import_customers(
    payload: ImportRequest,
    db: Session = Depends(get_db),
    member: Member = Depends(customers_member),
    _: None = Depends(require_csrf),
) -> ImportReport:
    try:
        return importer.run_import(db, member, payload.filename, payload.content, payload.mapping, dry_run=payload.dry_run)
    except importer.ImportFailure as error:
        raise HTTPException(status_code=422, detail=error.detail) from None


@router.get("/{customer_id}", response_model=CustomerItem)
def read_customer(customer_id: UUID, db: Session = Depends(get_db), member: Member = Depends(customers_member)) -> CustomerItem:
    try:
        return get_customer(db, member, customer_id)
    except CustomerError as error:
        _raise(error)


@router.get("/{customer_id}/overview", response_model=CustomerDetail)
def read_overview(customer_id: UUID, db: Session = Depends(get_db), member: Member = Depends(customers_member)) -> CustomerDetail:
    try:
        customer = owned_customer(db, member, customer_id)
    except CustomerError as error:
        _raise(error)
    return CustomerDetail(customer=get_customer(db, member, customer_id), overview=customer_overview(db, member, customer))


@router.put("/{customer_id}", response_model=CustomerItem)
def change_customer(
    customer_id: UUID,
    payload: CustomerInput,
    db: Session = Depends(get_db),
    member: Member = Depends(customers_member),
    _: None = Depends(require_csrf),
) -> CustomerItem:
    try:
        return update_customer(db, member, customer_id, payload)
    except CustomerError as error:
        _raise(error)


@router.delete("/{customer_id}", status_code=204)
def remove_customer(
    customer_id: UUID,
    db: Session = Depends(get_db),
    member: Member = Depends(customers_member),
    _: None = Depends(require_csrf),
) -> Response:
    try:
        delete_customer(db, member, customer_id)
    except CustomerError as error:
        _raise(error)
    return Response(status_code=204)
