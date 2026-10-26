"""Product recipes: the materials needed to make one unit of a product.

Recipes may nest (a sub-assembly can have its own recipe) but may never loop back to
the product being made, directly or through another recipe.
"""

import uuid
from collections import defaultdict
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.identity import AuditLog
from app.modules.inventory.models import Product
from app.modules.inventory.service import WHOLE_UNITS, quantity_text
from app.modules.production.models import RecipeItem
from app.modules.production.schemas import MaterialInput, RecipeInput, RecipeLine, RecipeOut, RecipeSummary
from app.services.auth import Member

MAX_ITEMS = 50
THOUSANDTH = Decimal("0.001")


class RecipeError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


def _product(db: Session, member: Member, product_id: uuid.UUID) -> Product:
    product = db.scalar(select(Product).where(Product.id == product_id, Product.company_id == member.company.id, Product.deleted_at.is_(None)))
    if product is None:
        raise RecipeError(404, "Ürün bulunamadı.")
    return product


def list_recipes(db: Session, member: Member) -> list[RecipeSummary]:
    rows = db.execute(
        select(Product, func.count(RecipeItem.id))
        .join(RecipeItem, RecipeItem.product_id == Product.id)
        .where(RecipeItem.company_id == member.company.id, Product.deleted_at.is_(None))
        .group_by(Product.id)
        .order_by(Product.name)
    ).all()
    return [RecipeSummary(product_id=product.id, name=product.name, sku=product.sku, unit=product.unit, materials=int(count)) for product, count in rows]


def read_recipe(db: Session, member: Member, product_id: uuid.UUID) -> RecipeOut:
    product = _product(db, member, product_id)
    rows = db.execute(
        select(RecipeItem, Product)
        .join(Product, Product.id == RecipeItem.material_id)
        .where(RecipeItem.company_id == member.company.id, RecipeItem.product_id == product.id)
        .order_by(RecipeItem.position)
    ).all()
    return RecipeOut(
        product_id=product.id,
        name=product.name,
        unit=product.unit,
        items=[
            RecipeLine(product_id=material.id, name=material.name, sku=material.sku, unit=material.unit, quantity=quantity_text(item.quantity), deleted=material.deleted_at is not None)
            for item, material in rows
        ],
    )


def _reaches(edges: dict[uuid.UUID, set[uuid.UUID]], start: set[uuid.UUID], target: uuid.UUID) -> bool:
    stack, seen = list(start), set()
    while stack:
        current = stack.pop()
        if current == target:
            return True
        if current in seen:
            continue
        seen.add(current)
        stack.extend(edges.get(current, ()))
    return False


def save_recipe(db: Session, member: Member, product_id: uuid.UUID, data: RecipeInput) -> RecipeOut:
    product = _product(db, member, product_id)
    wanted = {item.product_id for item in data.items}
    if len(wanted) != len(data.items):
        raise RecipeError(422, "Aynı malzeme iki kez eklendi; miktarları tek satırda birleştirin.")
    if product.id in wanted:
        raise RecipeError(422, "Bir ürün kendi reçetesinde malzeme olamaz.")
    if wanted:
        found = set(db.scalars(select(Product.id).where(Product.id.in_(wanted), Product.company_id == member.company.id, Product.deleted_at.is_(None))))
        if found != wanted:
            raise RecipeError(422, "Malzemelerden biri bulunamadı.")
        edges: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
        for parent, child in db.execute(select(RecipeItem.product_id, RecipeItem.material_id).where(RecipeItem.company_id == member.company.id)).all():
            if parent != product.id:
                edges[parent].add(child)
        if _reaches(edges, wanted, product.id):
            raise RecipeError(409, "Bu reçete döngü oluşturur: malzemelerden biri bu ürünle üretiliyor.")
    db.execute(delete(RecipeItem).where(RecipeItem.company_id == member.company.id, RecipeItem.product_id == product.id))
    for position, item in enumerate(data.items, start=1):
        db.add(RecipeItem(company_id=member.company.id, product_id=product.id, material_id=item.product_id, quantity=item.quantity, position=position))
    db.add(
        AuditLog(
            company_id=member.company.id,
            actor_user_id=member.user.id,
            action="production.recipe_saved" if data.items else "production.recipe_removed",
            entity_type="product",
            entity_id=str(product.id),
            summary={"name": product.name, "materials": len(data.items)},
            source="api",
        )
    )
    db.commit()
    return read_recipe(db, member, product.id)


def recipe_products(db: Session, company_id: uuid.UUID, product_ids: set[uuid.UUID] | None = None) -> set[uuid.UUID]:
    statement = select(RecipeItem.product_id).where(RecipeItem.company_id == company_id).distinct()
    if product_ids is not None:
        statement = statement.where(RecipeItem.product_id.in_(product_ids))
    return set(db.scalars(statement))


def materials_for(db: Session, member: Member, product_id: uuid.UUID, quantity: Decimal) -> list[MaterialInput]:
    """Recipe materials scaled to `quantity`; whole units are rounded up."""
    rows = db.execute(
        select(RecipeItem.material_id, RecipeItem.quantity, Product.unit)
        .join(Product, Product.id == RecipeItem.material_id)
        .where(RecipeItem.company_id == member.company.id, RecipeItem.product_id == product_id, Product.deleted_at.is_(None))
        .order_by(RecipeItem.position)
    ).all()
    lines = []
    for material_id, per_unit, unit in rows:
        needed = per_unit * quantity
        needed = needed.to_integral_value(rounding=ROUND_CEILING) if unit in WHOLE_UNITS else needed.quantize(THOUSANDTH, rounding=ROUND_CEILING)
        lines.append(MaterialInput(product_id=material_id, quantity=needed))
    return lines
