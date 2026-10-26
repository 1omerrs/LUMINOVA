import uuid
from datetime import UTC, datetime

from sqlalchemy import func, literal, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.identity import AuditLog
from app.modules.customers.models import Customer
from app.modules.customers.schemas import CustomerInput, CustomerItem, CustomerPage, CustomerSort
from app.services.auth import Member
from app.services.automation import emit

DUPLICATE_EMAIL = "Bu e-posta adresiyle kayıtlı bir müşteri zaten var."
_TURKISH = "tr-TR-x-icu"
_ORDER = {
    "name": (Customer.name.collate(_TURKISH).asc(), Customer.id.asc()),
    "-name": (Customer.name.collate(_TURKISH).desc(), Customer.id.desc()),
    "created_at": (Customer.created_at.asc(), Customer.id.asc()),
    "-created_at": (Customer.created_at.desc(), Customer.id.desc()),
}


class CustomerError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


def list_customers(db: Session, member: Member, *, query: str | None, sort: CustomerSort, page: int, page_size: int) -> CustomerPage:
    filters = [Customer.company_id == member.company.id, Customer.deleted_at.is_(None)]
    term = (query or "").strip()
    if term:
        pattern = f"%{term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')}%"
        turkish_name = func.lower(Customer.name.collate(_TURKISH))
        turkish_term = func.lower(literal(pattern).collate(_TURKISH))
        filters.append(
            or_(
                turkish_name.like(turkish_term, escape="\\"),
                Customer.email.ilike(pattern, escape="\\"),
                Customer.phone.ilike(pattern, escape="\\"),
            )
        )
    total = db.scalar(select(func.count()).select_from(Customer).where(*filters)) or 0
    rows = db.scalars(select(Customer).where(*filters).order_by(*_ORDER[sort]).offset((page - 1) * page_size).limit(page_size))
    return CustomerPage(items=[_item(row) for row in rows], total=int(total), page=page, page_size=page_size)


def get_customer(db: Session, member: Member, customer_id: uuid.UUID) -> CustomerItem:
    return _item(_owned(db, member, customer_id))


def create_customer(db: Session, member: Member, data: CustomerInput) -> CustomerItem:
    _reject_duplicate_email(db, member, data.email, None)
    customer = Customer(
        id=uuid.uuid4(),
        company_id=member.company.id,
        name=data.name,
        email=data.email,
        phone=data.phone,
        note=data.note,
        created_by=member.user.id,
    )
    db.add(customer)
    db.add(_audit(member, "customer.created", customer.id, sorted(data.model_dump(exclude_none=True))))
    emit(db, member, "customer.created", {"id": str(customer.id), "name": customer.name, "email": customer.email, "phone": customer.phone})
    _commit(db)
    db.refresh(customer)
    return _item(customer)


def update_customer(db: Session, member: Member, customer_id: uuid.UUID, data: CustomerInput) -> CustomerItem:
    customer = _owned(db, member, customer_id, lock=True)
    _reject_duplicate_email(db, member, data.email, customer.id)
    changed = [field for field, value in data.model_dump().items() if getattr(customer, field) != value]
    if changed:
        for field in changed:
            setattr(customer, field, getattr(data, field))
        customer.updated_at = datetime.now(UTC)
        db.add(_audit(member, "customer.updated", customer.id, changed))
        _commit(db)
    return _item(customer)


def delete_customer(db: Session, member: Member, customer_id: uuid.UUID) -> None:
    customer = _owned(db, member, customer_id, lock=True)
    now = datetime.now(UTC)
    customer.deleted_at = now
    customer.updated_at = now
    db.add(_audit(member, "customer.deleted", customer.id, []))
    db.commit()


def owned_customer(db: Session, member: Member, customer_id: uuid.UUID) -> Customer:
    return _owned(db, member, customer_id)


def _owned(db: Session, member: Member, customer_id: uuid.UUID, *, lock: bool = False) -> Customer:
    statement = select(Customer).where(
        Customer.id == customer_id,
        Customer.company_id == member.company.id,
        Customer.deleted_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    customer = db.scalar(statement)
    if customer is None:
        raise CustomerError(404, "Müşteri bulunamadı.")
    return customer


def _reject_duplicate_email(db: Session, member: Member, email: str | None, own_id: uuid.UUID | None) -> None:
    if email is None:
        return
    statement = select(Customer.id).where(
        Customer.company_id == member.company.id,
        Customer.deleted_at.is_(None),
        func.lower(Customer.email) == email.lower(),
    )
    if own_id is not None:
        statement = statement.where(Customer.id != own_id)
    if db.scalar(statement) is not None:
        raise CustomerError(409, DUPLICATE_EMAIL)


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if "uq_customers_company_id_email" in str(error.orig):
            raise CustomerError(409, DUPLICATE_EMAIL) from None
        raise


def _audit(member: Member, action: str, customer_id: uuid.UUID, fields: list[str]) -> AuditLog:
    return AuditLog(
        company_id=member.company.id,
        actor_user_id=member.user.id,
        action=action,
        entity_type="customer",
        entity_id=str(customer_id),
        summary={"fields": fields},
        source="api",
    )


def _item(customer: Customer) -> CustomerItem:
    return CustomerItem(
        id=customer.id,
        name=customer.name,
        email=customer.email,
        phone=customer.phone,
        note=customer.note,
        created_at=customer.created_at,
        updated_at=customer.updated_at,
    )
