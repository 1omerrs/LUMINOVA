import calendar
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, cast, func, select, text
from sqlalchemy.orm import Session

from app.modules.customers.models import Customer
from app.modules.finance.models import OPEN_STATUSES, FinancialRecord
from app.modules.finance.service import money
from app.modules.inventory.models import Product, StockMovement
from app.modules.inventory.service import quantity_label
from app.modules.production.models import ProductionOrder
from app.modules.projects.models import Project
from app.modules.reporting.schemas import (
    CustomersReport,
    FinanceReport,
    InventoryReport,
    Point,
    ProductionReport,
    ProjectsReport,
    Ranked,
    ReportOverview,
    SalesReport,
    TasksReport,
)
from app.modules.sales.models import OrderItem, SalesOrder
from app.modules.tasks.models import Task
from app.modules.tasks.service import company_today
from app.services.auth import Member
from app.services.modules import visible_keys

_MONTH_NAMES = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")
_FIRST_COLUMN = text("1")
_LOW = (Product.min_stock > 0) & (Product.stock_quantity < Product.min_stock)


def _months(today: date, count: int) -> list[date]:
    year, month = today.year, today.month
    result = []
    for _ in range(count):
        result.append(date(year, month, 1))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(result))


def _key(expr):
    return func.to_char(func.date_trunc("month", expr), "YYYY-MM")


def _series(db: Session, statement, keys: list[str], *, as_money: bool) -> list[Point]:
    found = {key: Decimal(value or 0) for key, value in db.execute(statement).all()}
    return [Point(month=key, value=money(found.get(key, Decimal(0))) if as_money else str(int(found.get(key, 0)))) for key in keys]


def _total(points: list[Point]) -> Decimal:
    return sum((Decimal(point.value) for point in points), Decimal(0))


def overview(db: Session, member: Member, months: int) -> ReportOverview:
    today = company_today(db, member)
    starts = _months(today, months)
    keys = [start.strftime("%Y-%m") for start in starts]
    start = starts[0]
    end = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    company = member.company.id

    def local_day(column):
        return cast(func.timezone(member.company.timezone, column), Date)

    enabled = visible_keys(db, member)
    report = ReportOverview(today=today, period_from=start, period_to=end, months=keys)

    if "sales" in enabled:
        counted = (SalesOrder.company_id == company, SalesOrder.status.in_(("confirmed", "fulfilled")), SalesOrder.order_date.between(start, end))
        try_orders = (*counted, SalesOrder.currency == "TRY")
        revenue = _series(
            db, select(_key(SalesOrder.order_date), func.sum(SalesOrder.total)).where(*try_orders).group_by(_FIRST_COLUMN), keys, as_money=True
        )
        orders = _series(db, select(_key(SalesOrder.order_date), func.count()).where(*counted).group_by(_FIRST_COLUMN), keys, as_money=False)
        order_count = int(_total(orders))
        try_count = db.scalar(select(func.count()).select_from(SalesOrder).where(*try_orders)) or 0
        total_revenue = _total(revenue)
        customers = db.execute(
            select(Customer.name, func.sum(SalesOrder.total), func.count())
            .join(Customer, Customer.id == SalesOrder.customer_id)
            .where(*try_orders)
            .group_by(Customer.id, Customer.name)
            .order_by(func.sum(SalesOrder.total).desc())
            .limit(5)
        ).all()
        products = db.execute(
            select(Product.name, Product.unit, func.sum(OrderItem.quantity))
            .join(SalesOrder, SalesOrder.id == OrderItem.order_id)
            .join(Product, Product.id == OrderItem.product_id)
            .where(*counted)
            .group_by(Product.id, Product.name, Product.unit)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(5)
        ).all()
        report.sales = SalesReport(
            revenue=revenue,
            orders=orders,
            total_revenue=money(total_revenue),
            order_count=order_count,
            average_order=money(total_revenue / try_count) if try_count else "0.00",
            open_orders=int(
                db.scalar(select(func.count()).select_from(SalesOrder).where(SalesOrder.company_id == company, SalesOrder.status.in_(("draft", "confirmed"))))
                or 0
            ),
            other_currency_orders=order_count - int(try_count),
            top_customers=[Ranked(label=name, value=money(total), detail=f"{count} sipariş") for name, total, count in customers],
            top_products=[Ranked(label=name, value=f"{quantity_label(qty)} {unit}") for name, unit, qty in products],
        )

    if "finance" in enabled:
        live = (FinancialRecord.company_id == company, FinancialRecord.status != "cancelled", FinancialRecord.currency == "TRY")
        in_period = (*live, FinancialRecord.record_date.between(start, end))

        def by_kind(kind: str) -> list[Point]:
            statement = select(_key(FinancialRecord.record_date), func.sum(FinancialRecord.amount)).where(*in_period, FinancialRecord.kind == kind).group_by(_FIRST_COLUMN)
            return _series(db, statement, keys, as_money=True)

        income, expense = by_kind("income"), by_kind("expense")
        pending = dict(
            db.execute(
                select(FinancialRecord.kind, func.sum(FinancialRecord.amount - FinancialRecord.paid_amount))
                .where(*live, FinancialRecord.status.in_(OPEN_STATUSES))
                .group_by(FinancialRecord.kind)
            ).all()
        )
        late = dict(
            db.execute(
                select(FinancialRecord.kind, func.count())
                .where(FinancialRecord.company_id == company, FinancialRecord.status.in_(OPEN_STATUSES), FinancialRecord.due_date < today)
                .group_by(FinancialRecord.kind)
            ).all()
        )
        categories = db.execute(
            select(FinancialRecord.category, func.sum(FinancialRecord.amount))
            .where(*in_period, FinancialRecord.kind == "expense")
            .group_by(FinancialRecord.category)
            .order_by(func.sum(FinancialRecord.amount).desc())
            .limit(6)
        ).all()
        report.finance = FinanceReport(
            income=income,
            expense=expense,
            total_income=money(_total(income)),
            total_expense=money(_total(expense)),
            net=money(_total(income) - _total(expense)),
            receivable=money(Decimal(pending.get("income") or 0)),
            payable=money(Decimal(pending.get("expense") or 0)),
            overdue_receivables=int(late.get("income", 0)),
            overdue_payables=int(late.get("expense", 0)),
            expense_categories=[Ranked(label=name, value=money(total)) for name, total in categories],
        )

    if "inventory" in enabled:
        scope = (Product.company_id == company, Product.deleted_at.is_(None))
        moves = (StockMovement.company_id == company, local_day(StockMovement.created_at).between(start, end))

        def moves_of(kind: str) -> list[Point]:
            statement = select(_key(local_day(StockMovement.created_at)), func.count()).where(*moves, StockMovement.kind == kind).group_by(_FIRST_COLUMN)
            return _series(db, statement, keys, as_money=False)

        low_items = db.execute(
            select(Product.name, Product.stock_quantity, Product.min_stock, Product.unit)
            .where(*scope, _LOW)
            .order_by((Product.stock_quantity / Product.min_stock).asc())
            .limit(5)
        ).all()
        report.inventory = InventoryReport(
            products=int(db.scalar(select(func.count()).select_from(Product).where(*scope)) or 0),
            low=int(db.scalar(select(func.count()).select_from(Product).where(*scope, _LOW)) or 0),
            low_items=[
                Ranked(label=name, value=f"{quantity_label(stock)} {unit}", detail=f"minimum {quantity_label(minimum)} {unit}") for name, stock, minimum, unit in low_items
            ],
            movements_in=moves_of("in"),
            movements_out=moves_of("out"),
        )

    if "tasks" in enabled:
        alive = (Task.company_id == company, Task.deleted_at.is_(None))
        created = _series(
            db,
            select(_key(local_day(Task.created_at)), func.count()).where(*alive, local_day(Task.created_at).between(start, end)).group_by(_FIRST_COLUMN),
            keys,
            as_money=False,
        )
        completed = _series(
            db,
            select(_key(local_day(Task.completed_at)), func.count()).where(*alive, Task.status == "done", local_day(Task.completed_at).between(start, end)).group_by(_FIRST_COLUMN),
            keys,
            as_money=False,
        )
        open_count = int(db.scalar(select(func.count()).select_from(Task).where(*alive, Task.status != "done")) or 0)
        made, done = _total(created), _total(completed)
        report.tasks = TasksReport(
            created=created,
            completed=completed,
            open=open_count,
            overdue=int(db.scalar(select(func.count()).select_from(Task).where(*alive, Task.status != "done", Task.due_date < today)) or 0),
            completion_rate=round(done * 100 / made) if made else 0,
        )

    if "projects" in enabled:
        alive = (Project.company_id == company, Project.deleted_at.is_(None))
        counts = dict(db.execute(select(Project.status, func.count()).where(*alive).group_by(Project.status)).all())
        task_stats = (
            select(Task.project_id, func.count().label("total"), func.count().filter(Task.status == "done").label("done"))
            .where(Task.company_id == company, Task.deleted_at.is_(None), Task.project_id.is_not(None))
            .group_by(Task.project_id)
            .subquery()
        )
        active = db.execute(
            select(Project.name, Project.due_date, task_stats.c.total, task_stats.c.done)
            .outerjoin(task_stats, task_stats.c.project_id == Project.id)
            .where(*alive, Project.status == "active")
        ).all()
        progress = [round(int(done or 0) * 100 / int(total)) if total else 0 for _, _, total, done in active]
        risky = sorted(
            (row for row in active if row[1] is not None and row[1] < today),
            key=lambda row: row[1],
        )[:5]
        report.projects = ProjectsReport(
            active=int(counts.get("active", 0)),
            planned=int(counts.get("planned", 0)),
            completed=int(counts.get("completed", 0)),
            average_progress=round(sum(progress) / len(progress)) if progress else 0,
            at_risk=[
                Ranked(label=name, value=f"%{round(int(done or 0) * 100 / int(total)) if total else 0}", detail=f"Teslim {due.day} {_MONTH_NAMES[due.month - 1]} {due.year}")
                for name, due, total, done in risky
            ],
        )

    if "production" in enabled:
        scope = (ProductionOrder.company_id == company,)
        report.production = ProductionReport(
            completed=_series(
                db,
                select(_key(local_day(ProductionOrder.completed_at)), func.count())
                .where(*scope, ProductionOrder.status == "completed", local_day(ProductionOrder.completed_at).between(start, end))
                .group_by(_FIRST_COLUMN),
                keys,
                as_money=False,
            ),
            open=int(db.scalar(select(func.count()).select_from(ProductionOrder).where(*scope, ProductionOrder.status.in_(("planned", "in_progress")))) or 0),
            completed_total=int(db.scalar(select(func.count()).select_from(ProductionOrder).where(*scope, ProductionOrder.status == "completed")) or 0),
        )

    if "customers" in enabled:
        alive = (Customer.company_id == company, Customer.deleted_at.is_(None))
        report.customers = CustomersReport(
            new=_series(
                db,
                select(_key(local_day(Customer.created_at)), func.count()).where(*alive, local_day(Customer.created_at).between(start, end)).group_by(_FIRST_COLUMN),
                keys,
                as_money=False,
            ),
            total=int(db.scalar(select(func.count()).select_from(Customer).where(*alive)) or 0),
        )

    return report
