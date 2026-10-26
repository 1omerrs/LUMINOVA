import uuid
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import and_, func, literal, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.identity import AuditLog, CompanyMembership, User
from app.modules.inventory.models import Product, StockMovement
from app.modules.inventory.schemas import (
    InventorySummary,
    MovementInput,
    MovementItem,
    MovementPage,
    ProductCreate,
    ProductInput,
    ProductItem,
    ProductPage,
    ProductSort,
    ReorderSuggestion,
)
from app.services.auth import Member
from app.services.automation import emit
from app.services.notifications import notify

DUPLICATE_SKU = "Bu stok koduyla kayıtlı bir ürün zaten var."
WHOLE_UNITS = {"adet", "paket", "kutu"}
USAGE_DAYS = 30
_TURKISH = "tr-TR-x-icu"
_ORDER = {
    "-created_at": (Product.created_at.desc(), Product.id.desc()),
    "name": (Product.name.collate(_TURKISH).asc(), Product.id.asc()),
    "-name": (Product.name.collate(_TURKISH).desc(), Product.id.desc()),
    "sku": (func.lower(Product.sku).asc(), Product.id.asc()),
    "stock": (Product.stock_quantity.asc(), Product.name.collate(_TURKISH).asc(), Product.id.asc()),
}
_LOW = and_(Product.min_stock > 0, Product.stock_quantity < Product.min_stock)
_CRITICAL = and_(
    or_(Product.critical_stock.is_not(None), Product.min_stock > 0),
    Product.stock_quantity <= func.coalesce(Product.critical_stock, Product.min_stock / 2),
)


LOW_FILTER = _LOW
CRITICAL_FILTER = _CRITICAL


def critical_level(product: Product) -> Decimal | None:
    """Stock at or below this level is critical. Without an explicit value it is half of the minimum."""
    if product.critical_stock is not None:
        return product.critical_stock
    return product.min_stock / 2 if product.min_stock > 0 else None


class InventoryError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


def quantity_text(value: Decimal) -> str:
    return format(value.normalize(), "f") if value != 0 else "0"


def quantity_label(value: Decimal) -> str:
    return quantity_text(value).replace(".", ",")


def list_products(
    db: Session,
    member: Member,
    *,
    query: str | None,
    sort: ProductSort,
    low_only: bool,
    page: int,
    page_size: int,
) -> ProductPage:
    filters = [Product.company_id == member.company.id, Product.deleted_at.is_(None)]
    term = (query or "").strip()
    if term:
        pattern = f"%{term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')}%"
        filters.append(
            or_(
                func.lower(Product.name.collate(_TURKISH)).like(func.lower(literal(pattern).collate(_TURKISH)), escape="\\"),
                Product.sku.ilike(pattern, escape="\\"),
            )
        )
    if low_only:
        filters.append(_LOW)
    total = db.scalar(select(func.count()).select_from(Product).where(*filters)) or 0
    rows = list(db.scalars(select(Product).where(*filters).order_by(*_ORDER[sort]).offset((page - 1) * page_size).limit(page_size)))
    ids = {row.id for row in rows}
    reserved = reserved_quantities(db, member.company.id, ids)
    incoming = incoming_quantities(db, member.company.id, ids)
    return ProductPage(items=[_product(row, reserved.get(row.id), incoming.get(row.id)) for row in rows], total=int(total), page=page, page_size=page_size)


def reserved_quantities(
    db: Session, company_id: uuid.UUID, product_ids: set[uuid.UUID] | None = None, *, exclude_order: uuid.UUID | None = None
) -> dict[uuid.UUID, Decimal]:
    """Quantities promised by confirmed sales orders not yet delivered and by open production orders' materials."""
    from app.modules.production.models import ProductionMaterial, ProductionOrder
    from app.modules.sales.models import OrderItem, SalesOrder

    if product_ids is not None and not product_ids:
        return {}
    totals: dict[uuid.UUID, Decimal] = {}
    materials = (
        select(ProductionMaterial.product_id, func.sum(ProductionMaterial.quantity))
        .join(ProductionOrder, ProductionOrder.id == ProductionMaterial.order_id)
        .where(ProductionOrder.company_id == company_id, ProductionOrder.status.in_(("planned", "in_progress")))
        .group_by(ProductionMaterial.product_id)
    )
    if product_ids is not None:
        materials = materials.where(ProductionMaterial.product_id.in_(product_ids))
    for product_id, amount in db.execute(materials).all():
        totals[product_id] = Decimal(amount)
    statement = (
        select(OrderItem.product_id, func.sum(OrderItem.quantity))
        .join(SalesOrder, SalesOrder.id == OrderItem.order_id)
        .where(
            SalesOrder.company_id == company_id,
            SalesOrder.status == "confirmed",
            SalesOrder.stock_posted_at.is_(None),
            OrderItem.product_id.is_not(None),
        )
        .group_by(OrderItem.product_id)
    )
    if product_ids is not None:
        statement = statement.where(OrderItem.product_id.in_(product_ids))
    if exclude_order is not None:
        statement = statement.where(SalesOrder.id != exclude_order)
    for product_id, amount in db.execute(statement).all():
        if product_id is not None:
            totals[product_id] = totals.get(product_id, Decimal(0)) + Decimal(amount)
    return totals


def incoming_quantities(db: Session, company_id: uuid.UUID, product_ids: set[uuid.UUID] | None = None) -> dict[uuid.UUID, Decimal]:
    """Quantities that planned or running production orders will add to stock."""
    from app.modules.production.models import ProductionOrder

    if product_ids is not None and not product_ids:
        return {}
    statement = (
        select(ProductionOrder.product_id, func.sum(ProductionOrder.quantity))
        .where(ProductionOrder.company_id == company_id, ProductionOrder.status.in_(("planned", "in_progress")))
        .group_by(ProductionOrder.product_id)
    )
    if product_ids is not None:
        statement = statement.where(ProductionOrder.product_id.in_(product_ids))
    return {product_id: Decimal(amount) for product_id, amount in db.execute(statement).all()}


def reorder_suggestions(db: Session, member: Member) -> list[ReorderSuggestion]:
    """Products whose expected stock falls below the minimum or will run out within two weeks at the recent pace."""
    from app.modules.production.recipes import recipe_products

    products = list(db.scalars(select(Product).where(Product.company_id == member.company.id, Product.deleted_at.is_(None))))
    if not products:
        return []
    ids = {product.id for product in products}
    held = reserved_quantities(db, member.company.id, ids)
    coming = incoming_quantities(db, member.company.id, ids)
    since = datetime.now(UTC) - timedelta(days=USAGE_DAYS)
    usage = dict(
        db.execute(
            select(StockMovement.product_id, func.sum(func.abs(StockMovement.quantity)))
            .where(StockMovement.company_id == member.company.id, StockMovement.kind == "out", StockMovement.created_at >= since)
            .group_by(StockMovement.product_id)
        ).all()
    )
    makeable = recipe_products(db, member.company.id, ids)
    found: list[tuple[Decimal, ReorderSuggestion]] = []
    for product in products:
        reserved = held.get(product.id, Decimal(0))
        incoming = coming.get(product.id, Decimal(0))
        expected = product.stock_quantity - reserved + incoming
        used = Decimal(usage.get(product.id) or 0)
        daily = used / USAGE_DAYS
        days_left = (product.stock_quantity - reserved) / daily if daily > 0 else None
        below = expected < product.min_stock or expected < 0
        running_out = days_left is not None and days_left < 14
        if not (below or running_out):
            continue
        target = max(product.min_stock, daily * USAGE_DAYS, Decimal(0))
        amount = target - expected
        if amount <= 0:
            continue
        amount = amount.to_integral_value(rounding=ROUND_CEILING) if product.unit in WHOLE_UNITS else amount.quantize(Decimal("0.001"), rounding=ROUND_CEILING)
        reasons = []
        if below:
            parts = [f"stok {quantity_label(product.stock_quantity)}"]
            if reserved:
                parts.append(f"siparişlere ve iş emirlerine ayrılan {quantity_label(reserved)}")
            if incoming:
                parts.append(f"üretimde {quantity_label(incoming)}")
            reasons.append(f"Beklenen {quantity_label(expected)} {product.unit}, minimum {quantity_label(product.min_stock)} ({', '.join(parts)}).")
        if used > 0:
            pace = f"Son {USAGE_DAYS} günde {quantity_label(used)} {product.unit} çıktı"
            reasons.append(f"{pace}; bu hızla yaklaşık {int(days_left)} gün yeter." if days_left is not None and days_left >= 0 else f"{pace}.")
        found.append(
            (
                expected - product.min_stock,
                ReorderSuggestion(
                    product_id=product.id,
                    name=product.name,
                    sku=product.sku,
                    unit=product.unit,
                    stock=quantity_text(product.stock_quantity),
                    reserved=quantity_text(reserved),
                    incoming=quantity_text(incoming),
                    expected=quantity_text(expected),
                    min_stock=quantity_text(product.min_stock),
                    used_last_30_days=quantity_text(used),
                    days_left=int(days_left) if days_left is not None and days_left >= 0 else None,
                    suggested=quantity_text(amount),
                    action="produce" if product.id in makeable else "purchase",
                    reasons=reasons,
                ),
            )
        )
    found.sort(key=lambda pair: pair[0])
    return [item for _, item in found]


def inventory_summary(db: Session, member: Member) -> InventorySummary:
    scope = (Product.company_id == member.company.id, Product.deleted_at.is_(None))
    products = db.scalar(select(func.count()).select_from(Product).where(*scope)) or 0
    low = db.scalar(select(func.count()).select_from(Product).where(*scope, _LOW)) or 0
    critical = db.scalar(select(func.count()).select_from(Product).where(*scope, _CRITICAL)) or 0
    return InventorySummary(products=int(products), low=int(low), critical=int(critical))


def _check_levels(unit: str, min_stock: Decimal, critical: Decimal | None) -> None:
    _require_whole(unit, min_stock, "Minimum stok")
    if critical is not None:
        _require_whole(unit, critical, "Kritik stok")
        if min_stock > 0 and critical > min_stock:
            raise InventoryError(422, "Kritik stok, minimum stoktan büyük olamaz.")


def get_product(db: Session, member: Member, product_id: uuid.UUID) -> ProductItem:
    return _held(db, member, _owned(db, member, product_id))


def create_product(db: Session, member: Member, data: ProductCreate) -> ProductItem:
    _check_levels(data.unit, data.min_stock, data.critical_stock)
    _require_whole(data.unit, data.initial_stock, "Açılış stoku")
    _reject_duplicate_sku(db, member, data.sku, None)
    product = Product(
        id=uuid.uuid4(),
        company_id=member.company.id,
        sku=data.sku,
        name=data.name,
        description=data.description,
        unit=data.unit,
        min_stock=data.min_stock,
        critical_stock=data.critical_stock,
        stock_quantity=data.initial_stock,
        created_by=member.user.id,
    )
    db.add(product)
    db.flush()
    if data.initial_stock > 0:
        db.add(
            StockMovement(
                company_id=member.company.id,
                product_id=product.id,
                kind="in",
                quantity=data.initial_stock,
                balance_after=data.initial_stock,
                note="Açılış stoku",
                created_by=member.user.id,
            )
        )
    db.add(_audit(member, "product.created", product.id, {"fields": sorted(data.model_dump(exclude_none=True))}))
    _commit(db)
    db.refresh(product)
    return _product(product)


def update_product(db: Session, member: Member, product_id: uuid.UUID, data: ProductInput) -> ProductItem:
    product = _owned(db, member, product_id, lock=True)
    _check_levels(data.unit, data.min_stock, data.critical_stock)
    if data.unit in WHOLE_UNITS and product.stock_quantity != product.stock_quantity.to_integral_value():
        raise InventoryError(422, "Mevcut stok tam sayı olmadığı için birim adet, paket veya kutu yapılamaz.")
    _reject_duplicate_sku(db, member, data.sku, product.id)
    changed = [field for field, value in data.model_dump().items() if getattr(product, field) != value]
    if changed:
        for field in changed:
            setattr(product, field, getattr(data, field))
        product.updated_at = datetime.now(UTC)
        db.add(_audit(member, "product.updated", product.id, {"fields": changed}))
        _commit(db)
    return _held(db, member, product)


def delete_product(db: Session, member: Member, product_id: uuid.UUID) -> None:
    product = _owned(db, member, product_id, lock=True)
    now = datetime.now(UTC)
    product.deleted_at = now
    product.updated_at = now
    db.add(_audit(member, "product.deleted", product.id, {}))
    db.commit()


def record_movement(db: Session, member: Member, product_id: uuid.UUID, data: MovementInput) -> tuple[ProductItem, MovementItem]:
    product = _owned(db, member, product_id, lock=True)
    if data.idempotency_key is not None:
        existing = _by_idempotency_key(db, member, data.idempotency_key)
        if existing is not None:
            if existing.product_id != product.id:
                raise InventoryError(409, "Bu işlem anahtarı başka bir ürün için kullanıldı.")
            return _held(db, member, product), _movement(existing, _actor_name(db, existing.created_by))

    _require_whole(product.unit, data.quantity, "Miktar")
    before = product.stock_quantity
    if data.kind == "adjustment":
        delta = data.quantity - before
        if delta == 0:
            raise InventoryError(422, "Sayılan miktar mevcut stokla aynı.")
    else:
        if data.quantity <= 0:
            raise InventoryError(422, "Miktar sıfırdan büyük olmalı.")
        delta = data.quantity if data.kind == "in" else -data.quantity
    if before + delta < 0:
        raise InventoryError(409, f"Stokta yeterli miktar yok. Mevcut stok: {quantity_label(before)} {product.unit}.")

    movement = post_stock_change(db, member, product, kind=data.kind, delta=delta, note=data.note, idempotency_key=data.idempotency_key)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if data.idempotency_key is not None and "uq_stock_movements_company_id_idempotency_key" in str(error.orig):
            existing = _by_idempotency_key(db, member, data.idempotency_key)
            if existing is not None and existing.product_id == product_id:
                return get_product(db, member, product_id), _movement(existing, _actor_name(db, existing.created_by))
            raise InventoryError(409, "Bu işlem anahtarı başka bir ürün için kullanıldı.") from None
        raise
    db.refresh(movement)
    return _held(db, member, product), _movement(movement, f"{member.user.first_name} {member.user.last_name}")


def lock_products(db: Session, member: Member, product_ids: set[uuid.UUID], *, include_deleted: bool = False) -> dict[uuid.UUID, Product]:
    statement = select(Product).where(Product.company_id == member.company.id, Product.id.in_(product_ids))
    if not include_deleted:
        statement = statement.where(Product.deleted_at.is_(None))
    rows = db.scalars(statement.order_by(Product.id).with_for_update())
    return {row.id: row for row in rows}


def post_stock_change(
    db: Session,
    member: Member,
    product: Product,
    *,
    kind: str,
    delta: Decimal,
    note: str | None,
    reference_type: str | None = None,
    reference_id: str | None = None,
    idempotency_key: str | None = None,
) -> StockMovement:
    """Write one movement for a product the caller has locked; the caller commits."""
    before = product.stock_quantity
    after = before + delta
    if after < 0:
        raise InventoryError(409, f"Stokta yeterli miktar yok. Mevcut stok: {quantity_label(before)} {product.unit}.")
    movement = StockMovement(
        id=uuid.uuid4(),
        company_id=member.company.id,
        product_id=product.id,
        kind=kind,
        quantity=delta,
        balance_after=after,
        note=note,
        reference_type=reference_type,
        reference_id=reference_id,
        idempotency_key=idempotency_key,
        created_by=member.user.id,
    )
    product.stock_quantity = after
    product.updated_at = datetime.now(UTC)
    db.add(movement)
    db.add(
        _audit(
            member,
            "stock.movement_recorded",
            product.id,
            {"kind": kind, "quantity": quantity_text(delta), "balance_after": quantity_text(after), "reference": reference_type},
        )
    )
    _alert_levels(db, member, product, movement, before, after)
    return movement


def _alert_levels(db: Session, member: Member, product: Product, movement: StockMovement, before: Decimal, after: Decimal) -> None:
    minimum = product.min_stock
    level = critical_level(product)
    if level is not None and before > level >= after:
        severity = "critical"
        title = f"{product.name} kritik seviyeye indi."
        body = f"Mevcut stok {quantity_label(after)} {product.unit}, kritik seviye {quantity_label(level)} {product.unit}"
        body += f", minimum {quantity_label(minimum)} {product.unit}." if minimum > 0 else "."
    elif minimum > 0 and before >= minimum > after:
        severity = "low"
        title = f"{product.name} minimum stok seviyesinin altına düştü."
        body = f"Mevcut stok {quantity_label(after)} {product.unit}, minimum {quantity_label(minimum)} {product.unit}."
    else:
        return
    recipients = {member.user.id}
    recipients.update(
        db.scalars(
            select(CompanyMembership.user_id).where(
                CompanyMembership.company_id == member.company.id,
                CompanyMembership.status == "active",
                CompanyMembership.role.in_(("owner", "admin")),
            )
        )
    )
    for user_id in sorted(recipients, key=str):
        notify(
            db,
            member,
            category="inventory",
            title=title,
            body=body,
            link="/panel/stok?kritik=1",
            dedupe_key=f"inventory.{severity}:{movement.id}",
            user_id=user_id,
        )
    emit(
        db,
        member,
        "stock.low",
        {
            "product_id": str(product.id),
            "sku": product.sku,
            "name": product.name,
            "unit": product.unit,
            "level": severity,
            "stock_quantity": quantity_text(after),
            "min_stock": quantity_text(minimum),
            "critical_stock": quantity_text(level) if level is not None else None,
        },
    )


def list_movements(db: Session, member: Member, product_id: uuid.UUID, *, page: int, page_size: int) -> MovementPage:
    product = _owned(db, member, product_id, include_deleted=True)
    scope = (StockMovement.company_id == member.company.id, StockMovement.product_id == product.id)
    total = db.scalar(select(func.count()).select_from(StockMovement).where(*scope)) or 0
    rows = db.execute(
        select(StockMovement, User.first_name, User.last_name)
        .outerjoin(User, User.id == StockMovement.created_by)
        .where(*scope)
        .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [_movement(row, f"{first} {last}" if first else None) for row, first, last in rows]
    return MovementPage(items=items, total=int(total), page=page, page_size=page_size)


def _owned(db: Session, member: Member, product_id: uuid.UUID, *, lock: bool = False, include_deleted: bool = False) -> Product:
    statement = select(Product).where(Product.id == product_id, Product.company_id == member.company.id)
    if not include_deleted:
        statement = statement.where(Product.deleted_at.is_(None))
    if lock:
        statement = statement.with_for_update()
    product = db.scalar(statement)
    if product is None:
        raise InventoryError(404, "Ürün bulunamadı.")
    return product


def _require_whole(unit: str, value: Decimal, label: str) -> None:
    if unit in WHOLE_UNITS and value != value.to_integral_value():
        raise InventoryError(422, f"{label} {unit.capitalize()} biriminde tam sayı olmalı.")


def _reject_duplicate_sku(db: Session, member: Member, sku: str, own_id: uuid.UUID | None) -> None:
    statement = select(Product.id).where(
        Product.company_id == member.company.id,
        Product.deleted_at.is_(None),
        func.lower(Product.sku) == sku.lower(),
    )
    if own_id is not None:
        statement = statement.where(Product.id != own_id)
    if db.scalar(statement) is not None:
        raise InventoryError(409, DUPLICATE_SKU)


def _by_idempotency_key(db: Session, member: Member, key: str) -> StockMovement | None:
    return db.scalar(
        select(StockMovement).where(StockMovement.company_id == member.company.id, StockMovement.idempotency_key == key)
    )


def _actor_name(db: Session, user_id: uuid.UUID | None) -> str | None:
    if user_id is None:
        return None
    user = db.get(User, user_id)
    return f"{user.first_name} {user.last_name}" if user else None


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if "uq_products_company_id_sku" in str(error.orig):
            raise InventoryError(409, DUPLICATE_SKU) from None
        raise


def _audit(member: Member, action: str, product_id: uuid.UUID, summary: dict[str, object]) -> AuditLog:
    return AuditLog(
        company_id=member.company.id,
        actor_user_id=member.user.id,
        action=action,
        entity_type="product",
        entity_id=str(product_id),
        summary=summary,
        source="api",
    )


def _held(db: Session, member: Member, product: Product) -> ProductItem:
    return _product(
        product,
        reserved_quantities(db, member.company.id, {product.id}).get(product.id),
        incoming_quantities(db, member.company.id, {product.id}).get(product.id),
    )


def _product(product: Product, reserved: Decimal | None = None, incoming: Decimal | None = None) -> ProductItem:
    held = reserved or Decimal(0)
    level = critical_level(product)
    return ProductItem(
        incoming=quantity_text(incoming or Decimal(0)),
        reserved=quantity_text(held),
        available=quantity_text(product.stock_quantity - held),
        id=product.id,
        sku=product.sku,
        name=product.name,
        description=product.description,
        unit=product.unit,
        min_stock=quantity_text(product.min_stock),
        critical_stock=quantity_text(product.critical_stock) if product.critical_stock is not None else None,
        critical_level=quantity_text(level) if level is not None else None,
        stock_quantity=quantity_text(product.stock_quantity),
        low=product.min_stock > 0 and product.stock_quantity < product.min_stock,
        critical=level is not None and product.stock_quantity <= level,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


def _movement(movement: StockMovement, actor: str | None) -> MovementItem:
    return MovementItem(
        id=movement.id,
        kind=movement.kind,
        quantity=quantity_text(movement.quantity),
        balance_after=quantity_text(movement.balance_after),
        note=movement.note,
        actor=actor,
        created_at=movement.created_at,
    )
