"""Per-company sales workflow rules that run inside an order transition.

Each rule is idempotent: an order never gets a second active income record, and a task
template is applied to an order at most once (task_template_runs target key).
"""

from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.identity import AuditLog
from app.modules.customers.models import Customer
from app.modules.finance.models import FinancialRecord
from app.modules.finance.schemas import RecordInput
from app.modules.finance.service import FinanceError, add_record, cancel_for_order
from app.modules.sales.models import SalesOrder, SalesRules
from app.modules.sales.schemas import SalesRulesInput, SalesRulesOut
from app.modules.inventory.service import WHOLE_UNITS, quantity_label
from app.modules.sales.service import CENT, SalesError, order_code, stock_check
from app.modules.tasks.errors import TaskError
from app.modules.tasks.models import TaskTemplate
from app.modules.tasks.service import company_today
from app.modules.tasks.workflow import already_applied, materialize
from app.services.auth import Member
from app.services.modules import enabled_keys


def _rules(db: Session, member: Member) -> SalesRules | None:
    return db.get(SalesRules, member.company.id)


def read_rules(db: Session, member: Member) -> SalesRulesOut:
    rules = _rules(db, member)
    enabled = enabled_keys(db, member)
    name = None
    if rules and rules.confirm_template_id:
        name = db.scalar(select(TaskTemplate.name).where(TaskTemplate.id == rules.confirm_template_id, TaskTemplate.deleted_at.is_(None)))
    return SalesRulesOut(
        income_on=rules.income_on if rules else "off",  # type: ignore[arg-type]
        income_due_days=rules.income_due_days if rules else None,
        confirm_template_id=rules.confirm_template_id if rules and name else None,
        confirm_template_name=name,
        production_on_shortage=rules.production_on_shortage if rules else False,
        finance_on="finance" in enabled,
        tasks_on="tasks" in enabled,
        production_on="production" in enabled,
        updated_at=rules.updated_at if rules else None,
    )


def save_rules(db: Session, member: Member, data: SalesRulesInput) -> SalesRulesOut:
    if data.confirm_template_id is not None:
        found = db.scalar(
            select(TaskTemplate.id).where(
                TaskTemplate.id == data.confirm_template_id, TaskTemplate.company_id == member.company.id, TaskTemplate.deleted_at.is_(None)
            )
        )
        if found is None:
            raise SalesError(422, "Seçilen görev şablonu bulunamadı.")
    rules = _rules(db, member) or SalesRules(company_id=member.company.id)
    rules.income_on = data.income_on
    rules.income_due_days = data.income_due_days
    rules.confirm_template_id = data.confirm_template_id
    rules.production_on_shortage = data.production_on_shortage
    rules.updated_by = member.user.id
    rules.updated_at = datetime.now(UTC)
    db.merge(rules)
    db.add(
        AuditLog(
            company_id=member.company.id,
            actor_user_id=member.user.id,
            action="sales.rules_updated",
            entity_type="sales_rules",
            entity_id=str(member.company.id),
            summary=data.model_dump(mode="json"),
            source="api",
        )
    )
    db.commit()
    return read_rules(db, member)


def _income(db: Session, member: Member, order: SalesOrder, rules: SalesRules) -> str | None:
    taken = db.scalar(
        select(FinancialRecord.id).where(
            FinancialRecord.company_id == member.company.id, FinancialRecord.order_id == order.id, FinancialRecord.status != "cancelled"
        )
    )
    if taken is not None or order.total <= 0:
        return None
    today = company_today(db, member)
    customer = db.scalar(select(Customer.name).where(Customer.id == order.customer_id))
    code = order_code(order.number)
    try:
        add_record(
            db,
            member,
            RecordInput(
                kind="income",
                category="Satış",
                description=f"{code} satışı",
                counterparty=customer,
                customer_id=order.customer_id,
                order_id=order.id,
                amount=order.total.quantize(CENT),
                currency=order.currency,  # type: ignore[arg-type]
                record_date=today,
                due_date=today + timedelta(days=rules.income_due_days) if rules.income_due_days is not None else None,
                note="Satış kuralıyla otomatik oluşturuldu.",
            ),
        )
    except FinanceError:
        return None
    amount = f"{order.total.quantize(CENT):,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return f"Gelir kaydı oluşturuldu: {amount} {order.currency}, ödeme bekliyor."


def _template(db: Session, member: Member, order: SalesOrder, rules: SalesRules) -> str | None:
    template = db.scalar(
        select(TaskTemplate).where(
            TaskTemplate.id == rules.confirm_template_id, TaskTemplate.company_id == member.company.id, TaskTemplate.deleted_at.is_(None)
        )
    )
    target = f"order:{order.id}"
    if template is None or already_applied(db, member, template.id, target):
        return None
    try:
        _, created = materialize(
            db,
            member,
            template,
            start=company_today(db, member),
            assignee_id=None,
            customer_id=order.customer_id,
            order_id=order.id,
            project_id=None,
            target_key=target,
        )
    except TaskError:
        return None
    return f"“{template.name}” şablonundan {len(created)} görev oluşturuldu."


def _production(db: Session, member: Member, order: SalesOrder) -> list[str]:
    from app.modules.production.models import ProductionOrder
    from app.modules.production.recipes import recipe_products
    from app.modules.production.schemas import ProductionInput
    from app.modules.production.service import ProductionError, add_order, production_code

    short = [check for check in stock_check(db, member, order) if Decimal(check.short) > 0]
    if not short:
        return []
    makeable = recipe_products(db, member.company.id, {check.product_id for check in short})
    code = order_code(order.number)
    notes = []
    for check in short:
        if check.product_id not in makeable:
            notes.append(f"{check.name} için reçete yok; eksik {check.short} {check.unit} için üretim emri açılamadı.")
            continue
        planned = db.scalar(
            select(func.coalesce(func.sum(ProductionOrder.quantity), 0)).where(
                ProductionOrder.company_id == member.company.id,
                ProductionOrder.sales_order_id == order.id,
                ProductionOrder.product_id == check.product_id,
                ProductionOrder.status != "cancelled",
            )
        )
        gap = Decimal(check.short) - Decimal(planned or 0)
        if gap <= 0:
            continue
        if check.unit in WHOLE_UNITS:
            gap = gap.to_integral_value(rounding=ROUND_CEILING)
        savepoint = db.begin_nested()
        try:
            made = add_order(
                db,
                member,
                ProductionInput(
                    product_id=check.product_id,
                    quantity=gap.quantize(Decimal("0.001")),
                    planned_date=company_today(db, member),
                    note=f"{code} siparişindeki eksik için satış kuralıyla açıldı.",
                    sales_order_id=order.id,
                ),
                automatic=True,
            )
            savepoint.commit()
        except ProductionError as error:
            savepoint.rollback()
            notes.append(f"{check.name} için üretim emri açılamadı: {error.detail}")
            continue
        notes.append(f"{production_code(made.number)} üretim emri açıldı: {quantity_label(gap)} {check.unit} {check.name}.")
    return notes


def on_transition(db: Session, member: Member, order: SalesOrder, to_status: str) -> list[str]:
    """Run the company's rules for an order that just moved to `to_status` (no commit)."""
    notes: list[str] = []
    enabled = enabled_keys(db, member)
    if to_status == "cancelled" and "finance" in enabled:
        cancelled, paid = cancel_for_order(db, member, order.id, f"{order_code(order.number)} iptal edildi.")
        if cancelled:
            notes.append(f"Bekleyen {cancelled} gelir kaydı iptal edildi.")
        if paid:
            notes.append("Ödenmiş gelir kaydı olduğu gibi bırakıldı; iade yaptıysanız Finans'ta ayrıca kaydedin.")
    rules = _rules(db, member)
    if rules is not None:
        if rules.income_on == to_status and "finance" in enabled:
            note = _income(db, member, order, rules)
            if note:
                notes.append(note)
        if to_status == "confirmed" and rules.confirm_template_id and "tasks" in enabled:
            note = _template(db, member, order, rules)
            if note:
                notes.append(note)
        if to_status == "confirmed" and rules.production_on_shortage and "production" in enabled:
            notes.extend(_production(db, member, order))
    if notes:
        db.add(
            AuditLog(
                company_id=member.company.id,
                actor_user_id=member.user.id,
                action="order.rules_applied",
                entity_type="order",
                entity_id=str(order.id),
                summary={"number": order.number, "notes": notes},
                source="api",
            )
        )
    return notes
