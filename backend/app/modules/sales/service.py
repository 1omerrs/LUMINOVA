import re
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, literal, or_, select
from sqlalchemy.orm import Session

from app.models.identity import AuditLog, Company, User
from app.modules.customers.models import Customer
from app.modules.inventory.models import Product
from app.modules.inventory.service import (
    InventoryError,
    WHOLE_UNITS,
    incoming_quantities,
    lock_products,
    post_stock_change,
    quantity_label,
    quantity_text,
    reserved_quantities,
)
from app.modules.quotes.models import Quote
from app.modules.sales.models import OrderItem, OrderStatusEvent, SalesOrder
from app.modules.sales.schemas import (
    OrderDetail,
    OrderEvent,
    OrderInput,
    OrderLine,
    OrderLineInput,
    OrderPage,
    OrderSort,
    OrderStatus,
    OrderSummaryItem,
    SalesSummary,
    StockCheck,
)
from app.services.auth import Member
from app.services.automation import emit

CENT = Decimal("0.01")
STATUS_LABELS = {"draft": "taslak", "confirmed": "onaylandı", "fulfilled": "teslim edildi", "cancelled": "iptal edildi"}
_TURKISH = "tr-TR-x-icu"
_CODE = re.compile(r"^(?:sp-?)?0*(\d{1,9})$", re.IGNORECASE)
_ORDER = {
    "-created_at": (SalesOrder.created_at.desc(), SalesOrder.id.desc()),
    "-order_date": (SalesOrder.order_date.desc(), SalesOrder.number.desc()),
    "order_date": (SalesOrder.order_date.asc(), SalesOrder.number.asc()),
    "-total": (SalesOrder.total.desc(), SalesOrder.number.desc()),
    "number": (SalesOrder.number.asc(),),
}


class SalesError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


def order_code(number: int) -> str:
    return f"SP-{number:04d}"


def money_text(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def price_line(quantity: Decimal, unit_price: Decimal, discount_rate: Decimal, vat_rate: int) -> tuple[Decimal, Decimal, Decimal]:
    """(discount, subtotal after discount, VAT) for one line, each rounded to cents."""
    gross = (quantity * unit_price).quantize(CENT, rounding=ROUND_HALF_UP)
    discount = (gross * discount_rate / Decimal(100)).quantize(CENT, rounding=ROUND_HALF_UP)
    subtotal = gross - discount
    vat = (subtotal * vat_rate / Decimal(100)).quantize(CENT, rounding=ROUND_HALF_UP)
    return discount, subtotal, vat


def _run_rules(db: Session, member: Member, order: SalesOrder, to_status: str) -> list[str]:
    from app.modules.sales.rules import on_transition

    return on_transition(db, member, order, to_status)


def list_orders(
    db: Session,
    member: Member,
    *,
    query: str | None,
    status: OrderStatus | None,
    sort: OrderSort,
    page: int,
    page_size: int,
) -> OrderPage:
    filters = [SalesOrder.company_id == member.company.id]
    if status is not None:
        filters.append(SalesOrder.status == status)
    term = (query or "").strip()
    if term:
        code = _CODE.match(term)
        pattern = f"%{term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')}%"
        by_name = func.lower(Customer.name.collate(_TURKISH)).like(func.lower(literal(pattern).collate(_TURKISH)), escape="\\")
        filters.append(or_(by_name, SalesOrder.number == int(code.group(1))) if code else by_name)
    counts = (
        select(OrderItem.order_id, func.count().label("item_count")).where(OrderItem.company_id == member.company.id).group_by(OrderItem.order_id).subquery()
    )
    base = select(SalesOrder, Customer.name, func.coalesce(counts.c.item_count, 0)).join(Customer, Customer.id == SalesOrder.customer_id).outerjoin(
        counts, counts.c.order_id == SalesOrder.id
    )
    total = db.scalar(select(func.count()).select_from(SalesOrder).join(Customer, Customer.id == SalesOrder.customer_id).where(*filters)) or 0
    rows = db.execute(base.where(*filters).order_by(*_ORDER[sort]).offset((page - 1) * page_size).limit(page_size)).all()
    return OrderPage(
        items=[_summary(order, name, int(count)) for order, name, count in rows],
        total=int(total),
        page=page,
        page_size=page_size,
    )


def sales_summary(db: Session, member: Member) -> SalesSummary:
    rows = db.execute(
        select(SalesOrder.status, func.count()).where(SalesOrder.company_id == member.company.id).group_by(SalesOrder.status)
    ).all()
    counts = {status: int(count) for status, count in rows}
    return SalesSummary(
        draft=counts.get("draft", 0),
        confirmed=counts.get("confirmed", 0),
        fulfilled=counts.get("fulfilled", 0),
        cancelled=counts.get("cancelled", 0),
    )


def get_order(db: Session, member: Member, order_id: uuid.UUID) -> OrderDetail:
    return _detail(db, member, _owned(db, member, order_id))


def create_order(db: Session, member: Member, data: OrderInput) -> OrderDetail:
    order = build_order(db, member, data)
    db.commit()
    return _detail(db, member, order)


def build_order(db: Session, member: Member, data: OrderInput) -> SalesOrder:
    """Add a draft order with its lines to the session; the caller commits."""
    customer = _customer(db, member, data.customer_id)
    db.execute(select(Company.id).where(Company.id == member.company.id).with_for_update())
    last = db.scalar(select(func.max(SalesOrder.number)).where(SalesOrder.company_id == member.company.id)) or 0
    order = SalesOrder(
        id=uuid.uuid4(),
        company_id=member.company.id,
        number=int(last) + 1,
        customer_id=customer.id,
        status="draft",
        currency=data.currency,
        order_date=data.order_date,
        note=data.note,
        created_by=member.user.id,
    )
    db.add(order)
    db.flush()
    _replace_lines(db, member, order, data.items)
    db.add(_event(member, order, None, "draft", None))
    db.add(_audit(member, "order.created", order, {"lines": len(data.items), "currency": data.currency}))
    db.flush()
    emit(db, member, "order.created", {**_event_data(order), "customer_name": customer.name, "lines": len(data.items)})
    return order


def _event_data(order: SalesOrder) -> dict[str, object]:
    return {
        "id": str(order.id),
        "number": order_code(order.number),
        "status": order.status,
        "customer_id": str(order.customer_id),
        "currency": order.currency,
        "total": money_text(order.total),
        "order_date": order.order_date.isoformat(),
    }


def update_order(db: Session, member: Member, order_id: uuid.UUID, data: OrderInput) -> OrderDetail:
    order = _owned(db, member, order_id, lock=True)
    if order.status != "draft":
        raise SalesError(409, "Yalnızca taslak siparişler düzenlenebilir.")
    customer = _customer(db, member, data.customer_id)
    order.customer_id = customer.id
    order.currency = data.currency
    order.order_date = data.order_date
    order.note = data.note
    order.updated_at = datetime.now(UTC)
    for item in db.scalars(select(OrderItem).where(OrderItem.order_id == order.id)):
        db.delete(item)
    db.flush()
    _replace_lines(db, member, order, data.items)
    db.add(_audit(member, "order.updated", order, {"lines": len(data.items)}))
    db.commit()
    return _detail(db, member, order)


def confirm_order(db: Session, member: Member, order_id: uuid.UUID, note: str | None) -> OrderDetail:
    order = _owned(db, member, order_id, lock=True)
    _require_status(order, {"draft"})
    _transition(db, member, order, "confirmed", note)
    notes = _run_rules(db, member, order, "confirmed")
    db.commit()
    return _detail(db, member, order, notes)


def fulfil_order(db: Session, member: Member, order_id: uuid.UUID, note: str | None) -> OrderDetail:
    order = _owned(db, member, order_id, lock=True)
    _require_status(order, {"confirmed"})
    if order.stock_posted_at is None:
        needed = _stock_needs(db, order)
        if needed:
            products = lock_products(db, member, set(needed))
            missing = [product_id for product_id in needed if product_id not in products]
            if missing:
                raise SalesError(409, "Siparişteki bir ürün silinmiş. Satırı düzenleyemediğiniz için siparişi iptal edip yeniden oluşturun.")
            shortages = [
                f"{products[pid].name} (mevcut {quantity_label(products[pid].stock_quantity)}, gereken {quantity_label(qty)} {products[pid].unit})"
                for pid, qty in needed.items()
                if products[pid].stock_quantity < qty
            ]
            if shortages:
                raise SalesError(409, f"Stok yetersiz: {'; '.join(shortages)}.")
            code = order_code(order.number)
            for pid, qty in needed.items():
                try:
                    post_stock_change(
                        db,
                        member,
                        products[pid],
                        kind="out",
                        delta=-qty,
                        note=f"{code} teslimatı",
                        reference_type="order",
                        reference_id=str(order.id),
                        idempotency_key=f"o:{order.id.hex}:out:{pid.hex}",
                    )
                except InventoryError as error:
                    raise SalesError(error.status_code, error.detail) from None
        order.stock_posted_at = datetime.now(UTC)
    _transition(db, member, order, "fulfilled", note)
    notes = _run_rules(db, member, order, "fulfilled")
    db.commit()
    return _detail(db, member, order, notes)


def cancel_order(db: Session, member: Member, order_id: uuid.UUID, note: str | None) -> OrderDetail:
    order = _owned(db, member, order_id, lock=True)
    _require_status(order, {"draft", "confirmed", "fulfilled"})
    if order.stock_posted_at is not None:
        needed = _stock_needs(db, order)
        products = lock_products(db, member, set(needed), include_deleted=True)
        code = order_code(order.number)
        for pid, qty in needed.items():
            if pid in products:
                post_stock_change(
                    db,
                    member,
                    products[pid],
                    kind="in",
                    delta=qty,
                    note=f"{code} iptali, stok iadesi",
                    reference_type="order_cancel",
                    reference_id=str(order.id),
                    idempotency_key=f"o:{order.id.hex}:ret:{pid.hex}",
                )
    _transition(db, member, order, "cancelled", note)
    notes = _run_rules(db, member, order, "cancelled")
    db.commit()
    return _detail(db, member, order, notes)


def _require_status(order: SalesOrder, allowed: set[str]) -> None:
    if order.status not in allowed:
        raise SalesError(409, f"Bu sipariş {STATUS_LABELS[order.status]} durumunda; bu işlem yapılamaz.")


def _transition(db: Session, member: Member, order: SalesOrder, to_status: str, note: str | None) -> None:
    now = datetime.now(UTC)
    previous = order.status
    order.status = to_status
    order.updated_at = now
    if to_status == "confirmed":
        order.confirmed_at = now
    elif to_status == "fulfilled":
        order.fulfilled_at = now
    elif to_status == "cancelled":
        order.cancelled_at = now
    db.add(_event(member, order, previous, to_status, note))
    db.add(_audit(member, "order.status_changed", order, {"from": previous, "to": to_status}))
    emit(db, member, "order.status_changed", {**_event_data(order), "previous_status": previous})


def _stock_needs(db: Session, order: SalesOrder) -> dict[uuid.UUID, Decimal]:
    needs: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    for item in db.scalars(select(OrderItem).where(OrderItem.order_id == order.id, OrderItem.product_id.is_not(None))):
        if item.product_id is not None:
            needs[item.product_id] += item.quantity
    return dict(sorted(needs.items(), key=lambda pair: str(pair[0])))


def _replace_lines(db: Session, member: Member, order: SalesOrder, lines: list[OrderLineInput]) -> None:
    product_ids = {line.product_id for line in lines if line.product_id is not None}
    products = {
        row.id: row
        for row in db.scalars(
            select(Product).where(Product.company_id == member.company.id, Product.id.in_(product_ids), Product.deleted_at.is_(None))
        )
    } if product_ids else {}
    subtotal = vat_total = discount_total = Decimal(0)
    for position, line in enumerate(lines, start=1):
        product = products.get(line.product_id) if line.product_id is not None else None
        if line.product_id is not None and product is None:
            raise SalesError(422, f"{position}. satırdaki ürün bulunamadı.")
        description = line.description or (product.name if product else "")
        if not description:
            raise SalesError(422, f"{position}. satır için ürün seçin veya açıklama yazın.")
        if product is not None and product.unit in WHOLE_UNITS and line.quantity != line.quantity.to_integral_value():
            raise SalesError(422, f"{position}. satır: {product.unit.capitalize()} biriminde miktar tam sayı olmalı.")
        line_discount, line_subtotal, line_vat = price_line(line.quantity, line.unit_price, line.discount_rate, line.vat_rate)
        subtotal += line_subtotal
        vat_total += line_vat
        discount_total += line_discount
        db.add(
            OrderItem(
                company_id=member.company.id,
                order_id=order.id,
                position=position,
                product_id=product.id if product else None,
                description=description[:200],
                quantity=line.quantity,
                unit_price=line.unit_price,
                vat_rate=line.vat_rate,
                discount_rate=line.discount_rate,
                line_discount=line_discount,
                line_subtotal=line_subtotal,
                line_vat=line_vat,
                line_total=line_subtotal + line_vat,
            )
        )
    order.subtotal = subtotal
    order.discount_total = discount_total
    order.vat_total = vat_total
    order.total = subtotal + vat_total


def _customer(db: Session, member: Member, customer_id: uuid.UUID) -> Customer:
    customer = db.scalar(
        select(Customer).where(Customer.id == customer_id, Customer.company_id == member.company.id, Customer.deleted_at.is_(None))
    )
    if customer is None:
        raise SalesError(422, "Seçilen müşteri bulunamadı.")
    return customer


def _owned(db: Session, member: Member, order_id: uuid.UUID, *, lock: bool = False) -> SalesOrder:
    statement = select(SalesOrder).where(SalesOrder.id == order_id, SalesOrder.company_id == member.company.id)
    if lock:
        statement = statement.with_for_update()
    order = db.scalar(statement)
    if order is None:
        raise SalesError(404, "Sipariş bulunamadı.")
    return order


def _event(member: Member, order: SalesOrder, from_status: str | None, to_status: str, note: str | None) -> OrderStatusEvent:
    return OrderStatusEvent(
        company_id=member.company.id,
        order_id=order.id,
        from_status=from_status,
        to_status=to_status,
        note=note.strip() if note and note.strip() else None,
        actor_user_id=member.user.id,
    )


def _audit(member: Member, action: str, order: SalesOrder, summary: dict[str, object]) -> AuditLog:
    return AuditLog(
        company_id=member.company.id,
        actor_user_id=member.user.id,
        action=action,
        entity_type="order",
        entity_id=str(order.id),
        summary={"number": order.number, **summary},
        source="api",
    )


def _summary(order: SalesOrder, customer_name: str, item_count: int) -> OrderSummaryItem:
    return OrderSummaryItem(
        id=order.id,
        number=order.number,
        code=order_code(order.number),
        customer_id=order.customer_id,
        customer_name=customer_name,
        status=order.status,
        currency=order.currency,
        order_date=order.order_date,
        total=money_text(order.total),
        item_count=item_count,
        created_at=order.created_at,
    )


def stock_check(db: Session, member: Member, order: SalesOrder) -> list[StockCheck]:
    """Per product: what this order needs against stock not already promised to other confirmed orders."""
    if order.stock_posted_at is not None or order.status not in {"draft", "confirmed"}:
        return []
    needed = _stock_needs(db, order)
    if not needed:
        return []
    products = {row.id: row for row in db.scalars(select(Product).where(Product.id.in_(needed.keys())))}
    held = reserved_quantities(db, member.company.id, set(needed), exclude_order=order.id)
    coming = incoming_quantities(db, member.company.id, set(needed))
    checks = []
    for product_id, quantity in needed.items():
        product = products.get(product_id)
        if product is None:
            continue
        free = product.stock_quantity - held.get(product_id, Decimal(0))
        checks.append(
            StockCheck(
                product_id=product_id,
                name=product.name,
                unit=product.unit,
                needed=quantity_text(quantity),
                on_hand=quantity_text(product.stock_quantity),
                reserved_elsewhere=quantity_text(held.get(product_id, Decimal(0))),
                available=quantity_text(free),
                short=quantity_text(max(quantity - free, Decimal(0))),
                incoming=quantity_text(coming.get(product_id, Decimal(0))),
            )
        )
    return checks


def _detail(db: Session, member: Member, order: SalesOrder, automation: list[str] | None = None) -> OrderDetail:
    customer_name = db.scalar(select(Customer.name).where(Customer.id == order.customer_id)) or ""
    source = db.execute(select(Quote.id, Quote.number).where(Quote.order_id == order.id, Quote.company_id == member.company.id)).first()
    lines = db.execute(
        select(OrderItem, Product.sku, Product.unit)
        .outerjoin(Product, Product.id == OrderItem.product_id)
        .where(OrderItem.order_id == order.id)
        .order_by(OrderItem.position)
    ).all()
    events = db.execute(
        select(OrderStatusEvent, User.first_name, User.last_name)
        .outerjoin(User, User.id == OrderStatusEvent.actor_user_id)
        .where(OrderStatusEvent.order_id == order.id)
        .order_by(OrderStatusEvent.created_at, OrderStatusEvent.id)
    ).all()
    summary = _summary(order, customer_name, len(lines))
    return OrderDetail(
        **summary.model_dump(),
        note=order.note,
        subtotal=money_text(order.subtotal),
        discount_total=money_text(order.discount_total),
        vat_total=money_text(order.vat_total),
        stock_posted=order.stock_posted_at is not None,
        source_quote_id=source[0] if source else None,
        source_quote_code=f"TK-{source[1]:04d}" if source else None,
        stock_check=stock_check(db, member, order),
        automation=automation or [],
        items=[
            OrderLine(
                id=item.id,
                position=item.position,
                product_id=item.product_id,
                product_sku=sku,
                product_unit=unit,
                description=item.description,
                quantity=quantity_text(item.quantity),
                unit_price=money_text(item.unit_price),
                vat_rate=item.vat_rate,
                discount_rate=quantity_text(item.discount_rate),
                line_discount=money_text(item.line_discount),
                line_subtotal=money_text(item.line_subtotal),
                line_vat=money_text(item.line_vat),
                line_total=money_text(item.line_total),
            )
            for item, sku, unit in lines
        ],
        events=[
            OrderEvent(
                from_status=event.from_status,
                to_status=event.to_status,
                note=event.note,
                actor=f"{first} {last}" if first else None,
                created_at=event.created_at,
            )
            for event, first, last in events
        ],
    )
