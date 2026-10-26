"""ORM models.

Import each model module here so Alembic can see its table metadata.
"""

from app.models.automation import AutomationEvent, WebhookDelivery, WebhookEndpoint
from app.models.closure import ClosureRequest
from app.models.identity import (
    AuditLog,
    Company,
    CompanyMembership,
    EmailVerificationToken,
    LoginAttempt,
    PasswordResetToken,
    Session,
    User,
)
from app.models.mail import EmailMessage
from app.models.modules import CompanyModule
from app.models.notifications import Notification, NotificationPreference
from app.models.support import SupportMessage, SupportTicket
from app.models.team import CompanyInvitation, JoinRequest, MemberPermission
from app.modules.customers.models import Customer
from app.modules.inventory.models import Product, StockMovement
from app.modules.finance.models import CashBalance, FinancialPayment, FinancialRecord, FinancialRecordRevision
from app.modules.production.models import ProductionMaterial, ProductionOrder, RecipeItem
from app.modules.projects.models import Project, ProjectMilestone, ProjectTemplate
from app.modules.quotes.models import Quote, QuoteItem
from app.modules.sales.models import OrderItem, OrderStatusEvent, SalesOrder, SalesRules
from app.modules.tasks.models import AutopilotSettings, Task, TaskDependency, TaskTemplate, TaskTemplateRun

__all__ = [
    "AutomationEvent",
    "ClosureRequest",
    "WebhookDelivery",
    "WebhookEndpoint",
    "CompanyInvitation",
    "MemberPermission",
    "JoinRequest",
    "CashBalance",
    "FinancialPayment",
    "FinancialRecord",
    "FinancialRecordRevision",
    "ProductionMaterial",
    "RecipeItem",
    "ProductionOrder",
    "Project",
    "ProjectMilestone",
    "ProjectTemplate",
    "Quote",
    "QuoteItem",
    "AutopilotSettings",
    "Task",
    "TaskDependency",
    "TaskTemplate",
    "TaskTemplateRun",
    "OrderItem",
    "OrderStatusEvent",
    "SalesOrder",
    "SalesRules",
    "AuditLog",
    "Company",
    "CompanyMembership",
    "CompanyModule",
    "Customer",
    "EmailMessage",
    "Product",
    "StockMovement",
    "EmailVerificationToken",
    "LoginAttempt",
    "Notification",
    "NotificationPreference",
    "PasswordResetToken",
    "Session",
    "SupportMessage",
    "SupportTicket",
    "User",
]
