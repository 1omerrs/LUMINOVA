from fastapi import APIRouter

from app.api.routes.account import router as account_router
from app.api.routes.activity import router as activity_router
from app.api.routes.admin import router as admin_router
from app.api.routes.automation import hooks as hooks_router
from app.api.routes.automation import router as automation_router
from app.api.routes.support import router as support_router
from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.mail import router as mail_router
from app.api.routes.modules import router as modules_router
from app.api.routes.insights import router as insights_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.team import router as team_router
from app.modules.customers.routes import router as customers_router
from app.modules.inventory.routes import router as inventory_router
from app.modules.finance.routes import router as finance_router
from app.modules.production.routes import router as production_router
from app.modules.projects.routes import router as projects_router
from app.modules.quotes.routes import public as public_quotes_router
from app.modules.quotes.routes import router as quotes_router
from app.modules.reporting.routes import router as reporting_router
from app.modules.sales.routes import router as sales_router
from app.modules.tasks.routes import router as tasks_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(modules_router, tags=["modules"])
api_router.include_router(notifications_router, tags=["notifications"])
api_router.include_router(insights_router, tags=["insights"])
api_router.include_router(team_router, tags=["team"])
api_router.include_router(activity_router, tags=["activity"])
api_router.include_router(account_router, tags=["account"])
api_router.include_router(support_router, tags=["support"])
api_router.include_router(admin_router, tags=["admin"])
api_router.include_router(automation_router, tags=["automation"])
api_router.include_router(hooks_router, tags=["automation"])
api_router.include_router(mail_router, tags=["mail"])
api_router.include_router(customers_router, tags=["customers"])
api_router.include_router(inventory_router, tags=["inventory"])
api_router.include_router(sales_router, tags=["sales"])
api_router.include_router(tasks_router, tags=["tasks"])
api_router.include_router(projects_router, tags=["projects"])
api_router.include_router(finance_router, tags=["finance"])
api_router.include_router(production_router, tags=["production"])
api_router.include_router(reporting_router, tags=["reporting"])
api_router.include_router(quotes_router, tags=["quotes"])
api_router.include_router(public_quotes_router, tags=["quotes"])
