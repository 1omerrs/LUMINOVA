import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, literal, or_, select
from sqlalchemy.orm import Session

from app.models.identity import AuditLog, Company, User
from app.modules.inventory.models import Product
from app.modules.inventory.service import WHOLE_UNITS, InventoryError, lock_products, post_stock_change, quantity_label, quantity_text
from app.modules.production.models import ProductionMaterial, ProductionOrder
from app.modules.production.schemas import (
    CancelInput,
    MaterialLine,
    ProductionDetail,
    ProductionInput,
    ProductionPage,
    ProductionSort,
    ProductionStatus,
    ProductionSummary,
    ProductionSummaryItem,
)
from app.services.auth import Member
from app.services.automation import emit

STATUS_LABELS = {"planned": "planlandı", "in_progress": "üretimde", "completed": "tamamlandı", "cancelled": "iptal edildi"}
_TURKISH = "tr-TR-x-icu"
_CODE = re.compile(r"^(?:ue-?)?0*(\d{1,9})$", re.IGNORECASE)
_ORDER = {
    "-created_at": (ProductionOrder.created_at.desc(), ProductionOrder.id.desc()),
    "planned_date": (ProductionOrder.planned_date.asc().nulls_last(), ProductionOrder.number.asc()),
    "number": (ProductionOrder.number.asc(),),
}


class ProductionError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


def production_code(number: int) -> str:
    return f"UE-{number:04d}"


def _material_stats(member: Member):
    return (
        select(
            ProductionMaterial.order_id.label("order_id"),
            func.count().label("materials"),
            func.count().filter(Product.stock_quantity < ProductionMaterial.quantity).label("short"),
        )
        .join(Product, Product.id == ProductionMaterial.product_id)
        .where(ProductionMaterial.company_id == member.company.id)
        .group_by(ProductionMaterial.order_id)
        .subquery()
    )


def list_orders(
    db: Session,
    member: Member,
    *,
    query: str | None,
    status: ProductionStatus | None,
    sort: ProductionSort,
    page: int,
    page_size: int,
) -> ProductionPage:
    filters = [ProductionOrder.company_id == member.company.id]
    if status is not None:
        filters.append(ProductionOrder.status == status)
    term = (query or "").strip()
    if term:
        code = _CODE.match(term)
        pattern = func.lower(literal(f"%{term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')}%").collate(_TURKISH))
        by_name = func.lower(Product.name.collate(_TURKISH)).like(pattern, escape="\\")
        filters.append(or_(by_name, ProductionOrder.number == int(code.group(1))) if code else by_name)
    stats = _material_stats(member)
    base = (
        select(ProductionOrder, Product, stats.c.materials, stats.c.short)
        .join(Product, Product.id == ProductionOrder.product_id)
        .outerjoin(stats, stats.c.order_id == ProductionOrder.id)
        .where(*filters)
    )
    total = db.scalar(select(func.count()).select_from(ProductionOrder).join(Product, Product.id == ProductionOrder.product_id).where(*filters)) or 0
    rows = db.execute(base.order_by(*_ORDER[sort]).offset((page - 1) * page_size).limit(page_size)).all()
    links = _links(db, [row[0] for row in rows])
    return ProductionPage(
        items=[_summary(order, product, int(count or 0), int(short or 0), links) for order, product, count, short in rows],
        total=int(total),
        page=page,
        page_size=page_size,
    )


def production_summary(db: Session, member: Member) -> ProductionSummary:
    rows = db.execute(
        select(ProductionOrder.status, func.count()).where(ProductionOrder.company_id == member.company.id).group_by(ProductionOrder.status)
    ).all()
    counts = {status: int(count) for status, count in rows}
    return ProductionSummary(
        planned=counts.get("planned", 0),
        in_progress=counts.get("in_progress", 0),
        completed=counts.get("completed", 0),
        cancelled=counts.get("cancelled", 0),
    )


def get_order(db: Session, member: Member, order_id: uuid.UUID) -> ProductionDetail:
    return _detail(db, member, _owned(db, member, order_id))


def create_order(db: Session, member: Member, data: ProductionInput) -> ProductionDetail:
    order = add_order(db, member, data)
    db.commit()
    return _detail(db, member, order)


def add_order(db: Session, member: Member, data: ProductionInput, *, automatic: bool = False) -> ProductionOrder:
    """Validate and add a planned production order to the session; the caller commits."""
    data = _with_recipe(db, member, data)
    output = _check_lines(db, member, data)
    _check_links(db, member, data)
    db.execute(select(Company.id).where(Company.id == member.company.id).with_for_update())
    last = db.scalar(select(func.max(ProductionOrder.number)).where(ProductionOrder.company_id == member.company.id)) or 0
    order = ProductionOrder(
        id=uuid.uuid4(),
        company_id=member.company.id,
        number=int(last) + 1,
        product_id=output.id,
        sales_order_id=data.sales_order_id,
        project_id=data.project_id,
        quantity=data.quantity,
        status="planned",
        planned_date=data.planned_date,
        note=data.note,
        created_by=member.user.id,
    )
    db.add(order)
    db.flush()
    _replace_materials(db, member, order, data)
    db.add(_audit(member, "production.created", order, {"materials": len(data.materials), "auto": automatic}))
    return order


def _with_recipe(db: Session, member: Member, data: ProductionInput) -> ProductionInput:
    if data.materials:
        return data
    from app.modules.production.recipes import materials_for

    materials = materials_for(db, member, data.product_id, data.quantity)
    if not materials:
        raise ProductionError(422, "Malzeme ekleyin veya bu ürün için önce reçete tanımlayın.")
    return data.model_copy(update={"materials": materials})


def _check_links(db: Session, member: Member, data: ProductionInput) -> None:
    from app.modules.projects.models import Project
    from app.modules.sales.models import SalesOrder

    if data.sales_order_id is not None and db.scalar(
        select(SalesOrder.id).where(SalesOrder.id == data.sales_order_id, SalesOrder.company_id == member.company.id)
    ) is None:
        raise ProductionError(422, "Bağlanan sipariş bulunamadı.")
    if data.project_id is not None and db.scalar(
        select(Project.id).where(Project.id == data.project_id, Project.company_id == member.company.id, Project.deleted_at.is_(None))
    ) is None:
        raise ProductionError(422, "Bağlanan proje bulunamadı.")


def update_order(db: Session, member: Member, order_id: uuid.UUID, data: ProductionInput) -> ProductionDetail:
    order = _owned(db, member, order_id, lock=True)
    if order.status != "planned":
        raise ProductionError(409, "Yalnızca planlanan iş emirleri düzenlenebilir.")
    kept = {field: getattr(order, field) for field in ("sales_order_id", "project_id") if field not in data.model_fields_set}
    data = _with_recipe(db, member, data.model_copy(update=kept))
    output = _check_lines(db, member, data)
    _check_links(db, member, data)
    order.product_id = output.id
    order.quantity = data.quantity
    order.planned_date = data.planned_date
    order.note = data.note
    order.sales_order_id = data.sales_order_id
    order.project_id = data.project_id
    order.updated_at = datetime.now(UTC)
    for material in db.scalars(select(ProductionMaterial).where(ProductionMaterial.order_id == order.id)):
        db.delete(material)
    db.flush()
    _replace_materials(db, member, order, data)
    db.add(_audit(member, "production.updated", order, {"materials": len(data.materials)}))
    db.commit()
    return _detail(db, member, order)


def start_order(db: Session, member: Member, order_id: uuid.UUID) -> ProductionDetail:
    order = _owned(db, member, order_id, lock=True)
    _require_status(order, {"planned"})
    now = datetime.now(UTC)
    order.status = "in_progress"
    order.started_at = now
    order.updated_at = now
    db.add(_audit(member, "production.started", order, {}))
    db.commit()
    return _detail(db, member, order)


def complete_order(db: Session, member: Member, order_id: uuid.UUID) -> ProductionDetail:
    order = _owned(db, member, order_id, lock=True)
    _require_status(order, {"planned", "in_progress"})
    materials = list(db.scalars(select(ProductionMaterial).where(ProductionMaterial.order_id == order.id).order_by(ProductionMaterial.position)))
    products = lock_products(db, member, {order.product_id, *(item.product_id for item in materials)})
    if order.product_id not in products or any(item.product_id not in products for item in materials):
        raise ProductionError(409, "İş emrindeki bir ürün silinmiş. İş emrini iptal edip yeniden oluşturun.")
    shortages = [
        f"{products[item.product_id].name} (mevcut {quantity_label(products[item.product_id].stock_quantity)}, gereken {quantity_label(item.quantity)} {products[item.product_id].unit})"
        for item in materials
        if products[item.product_id].stock_quantity < item.quantity
    ]
    if shortages:
        raise ProductionError(409, f"Malzeme yetersiz: {'; '.join(shortages)}.")
    code = production_code(order.number)
    try:
        for item in materials:
            post_stock_change(
                db,
                member,
                products[item.product_id],
                kind="out",
                delta=-item.quantity,
                note=f"{code} üretim tüketimi",
                reference_type="production",
                reference_id=str(order.id),
                idempotency_key=f"p:{order.id.hex}:use:{item.product_id.hex}",
            )
        post_stock_change(
            db,
            member,
            products[order.product_id],
            kind="in",
            delta=order.quantity,
            note=f"{code} üretim çıkışı",
            reference_type="production",
            reference_id=str(order.id),
            idempotency_key=f"p:{order.id.hex}:make:{order.product_id.hex}",
        )
    except InventoryError as error:
        raise ProductionError(error.status_code, error.detail) from None
    now = datetime.now(UTC)
    order.status = "completed"
    order.started_at = order.started_at or now
    order.completed_at = now
    order.stock_posted_at = now
    order.updated_at = now
    db.add(_audit(member, "production.completed", order, {"materials": len(materials)}))
    emit(
        db,
        member,
        "production.completed",
        {"id": str(order.id), "number": code, "product_id": str(order.product_id), "quantity": quantity_text(order.quantity), "materials": len(materials)},
    )
    db.commit()
    return _detail(db, member, order)


def cancel_order(db: Session, member: Member, order_id: uuid.UUID, data: CancelInput) -> ProductionDetail:
    order = _owned(db, member, order_id, lock=True)
    if order.status == "completed":
        raise ProductionError(409, "Tamamlanan iş emri iptal edilemez. Stok düzeltmesi için Stok ve Depo modülünde sayım kaydı girin.")
    _require_status(order, {"planned", "in_progress"})
    now = datetime.now(UTC)
    order.status = "cancelled"
    order.cancel_reason = data.reason
    order.cancelled_at = now
    order.updated_at = now
    db.add(_audit(member, "production.cancelled", order, {}))
    db.commit()
    return _detail(db, member, order)


def _require_status(order: ProductionOrder, allowed: set[str]) -> None:
    if order.status not in allowed:
        raise ProductionError(409, f"Bu iş emri {STATUS_LABELS[order.status]} durumunda; bu işlem yapılamaz.")


def _check_lines(db: Session, member: Member, data: ProductionInput) -> Product:
    ids = {data.product_id, *(item.product_id for item in data.materials)}
    products = {
        row.id: row
        for row in db.scalars(select(Product).where(Product.company_id == member.company.id, Product.id.in_(ids), Product.deleted_at.is_(None)))
    }
    output = products.get(data.product_id)
    if output is None:
        raise ProductionError(422, "Üretilecek ürün bulunamadı.")
    if output.unit in WHOLE_UNITS and data.quantity != data.quantity.to_integral_value():
        raise ProductionError(422, f"Üretim miktarı {output.unit.capitalize()} biriminde tam sayı olmalı.")
    seen: set[uuid.UUID] = set()
    for position, item in enumerate(data.materials, start=1):
        material = products.get(item.product_id)
        if material is None:
            raise ProductionError(422, f"{position}. malzeme bulunamadı.")
        if item.product_id == data.product_id:
            raise ProductionError(422, "Üretilen ürün kendi malzemesi olamaz.")
        if item.product_id in seen:
            raise ProductionError(422, f"{material.name} iki kez eklendi; miktarları tek satırda birleştirin.")
        if material.unit in WHOLE_UNITS and item.quantity != item.quantity.to_integral_value():
            raise ProductionError(422, f"{position}. malzeme: {material.unit.capitalize()} biriminde miktar tam sayı olmalı.")
        seen.add(item.product_id)
    return output


def _replace_materials(db: Session, member: Member, order: ProductionOrder, data: ProductionInput) -> None:
    for position, item in enumerate(data.materials, start=1):
        db.add(
            ProductionMaterial(
                company_id=member.company.id,
                order_id=order.id,
                position=position,
                product_id=item.product_id,
                quantity=item.quantity,
            )
        )


def _owned(db: Session, member: Member, order_id: uuid.UUID, *, lock: bool = False) -> ProductionOrder:
    statement = select(ProductionOrder).where(ProductionOrder.id == order_id, ProductionOrder.company_id == member.company.id)
    if lock:
        statement = statement.with_for_update()
    order = db.scalar(statement)
    if order is None:
        raise ProductionError(404, "İş emri bulunamadı.")
    return order


def _audit(member: Member, action: str, order: ProductionOrder, summary: dict[str, object]) -> AuditLog:
    return AuditLog(
        company_id=member.company.id,
        actor_user_id=member.user.id,
        action=action,
        entity_type="production_order",
        entity_id=str(order.id),
        summary={"number": order.number, **summary},
        source="api",
    )


def _links(db: Session, orders: list[ProductionOrder]) -> dict[uuid.UUID, str]:
    from app.modules.projects.models import Project
    from app.modules.sales.models import SalesOrder

    sales = {order.sales_order_id for order in orders if order.sales_order_id}
    projects = {order.project_id for order in orders if order.project_id}
    names: dict[uuid.UUID, str] = {}
    if sales:
        names.update({key: f"SP-{number:04d}" for key, number in db.execute(select(SalesOrder.id, SalesOrder.number).where(SalesOrder.id.in_(sales))).all()})
    if projects:
        names.update(dict(db.execute(select(Project.id, Project.name).where(Project.id.in_(projects))).all()))
    return names


def _summary(order: ProductionOrder, product: Product, material_count: int, short: int, links: dict[uuid.UUID, str] | None = None) -> ProductionSummaryItem:
    links = links or {}
    return ProductionSummaryItem(
        sales_order_id=order.sales_order_id,
        sales_order_code=links.get(order.sales_order_id) if order.sales_order_id else None,
        project_id=order.project_id,
        project_name=links.get(order.project_id) if order.project_id else None,
        id=order.id,
        number=order.number,
        code=production_code(order.number),
        product_id=product.id,
        product_name=product.name,
        product_sku=product.sku,
        unit=product.unit,
        quantity=quantity_text(order.quantity),
        status=order.status,
        planned_date=order.planned_date,
        material_count=material_count,
        shortage=short > 0 and order.status in {"planned", "in_progress"},
        created_at=order.created_at,
    )


def _detail(db: Session, member: Member, order: ProductionOrder) -> ProductionDetail:
    db.refresh(order)
    product = db.get(Product, order.product_id)
    rows = db.execute(
        select(ProductionMaterial, Product)
        .join(Product, Product.id == ProductionMaterial.product_id)
        .where(ProductionMaterial.order_id == order.id)
        .order_by(ProductionMaterial.position)
    ).all()
    open_order = order.status in {"planned", "in_progress"}
    materials = [
        MaterialLine(
            product_id=item.product_id,
            name=material.name,
            sku=material.sku,
            unit=material.unit,
            quantity=quantity_text(item.quantity),
            available=quantity_text(material.stock_quantity),
            short=open_order and material.stock_quantity < item.quantity,
        )
        for item, material in rows
    ]
    if product is None:
        raise ProductionError(404, "Üretilecek ürün bulunamadı.")
    creator = db.execute(select(User.first_name, User.last_name).where(User.id == order.created_by)).first() if order.created_by else None
    summary = _summary(order, product, len(materials), sum(1 for line in materials if line.short), _links(db, [order]))
    return ProductionDetail(
        **summary.model_dump(),
        note=order.note,
        cancel_reason=order.cancel_reason,
        product_stock=quantity_text(product.stock_quantity),
        stock_posted=order.stock_posted_at is not None,
        started_at=order.started_at,
        completed_at=order.completed_at,
        cancelled_at=order.cancelled_at,
        created_by=f"{creator[0]} {creator[1]}" if creator else None,
        materials=materials,
    )
