from datetime import date

from pydantic import BaseModel


class Point(BaseModel):
    month: str
    value: str


class Ranked(BaseModel):
    label: str
    value: str
    detail: str | None = None


class SalesReport(BaseModel):
    revenue: list[Point]
    orders: list[Point]
    total_revenue: str
    order_count: int
    average_order: str
    open_orders: int
    other_currency_orders: int
    top_customers: list[Ranked]
    top_products: list[Ranked]


class FinanceReport(BaseModel):
    income: list[Point]
    expense: list[Point]
    total_income: str
    total_expense: str
    net: str
    receivable: str
    payable: str
    overdue_receivables: int
    overdue_payables: int
    expense_categories: list[Ranked]


class InventoryReport(BaseModel):
    products: int
    low: int
    low_items: list[Ranked]
    movements_in: list[Point]
    movements_out: list[Point]


class TasksReport(BaseModel):
    created: list[Point]
    completed: list[Point]
    open: int
    overdue: int
    completion_rate: int


class ProjectsReport(BaseModel):
    active: int
    planned: int
    completed: int
    average_progress: int
    at_risk: list[Ranked]


class ProductionReport(BaseModel):
    completed: list[Point]
    open: int
    completed_total: int


class CustomersReport(BaseModel):
    new: list[Point]
    total: int


class ReportOverview(BaseModel):
    today: date
    period_from: date
    period_to: date
    months: list[str]
    sales: SalesReport | None = None
    finance: FinanceReport | None = None
    inventory: InventoryReport | None = None
    tasks: TasksReport | None = None
    projects: ProjectsReport | None = None
    production: ProductionReport | None = None
    customers: CustomersReport | None = None
