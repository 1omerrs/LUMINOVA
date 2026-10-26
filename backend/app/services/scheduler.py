"""Periodic work that must happen even when nobody has the panel open.

Runs automatic-task sync once per company (as its owner), due reminders for every
active member and, on Monday from 09:00, the weekly digest. Every step is idempotent,
so overlapping runs are harmless.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.identity import Company, CompanyMembership, User
from app.services.auth import Member
from app.services.digest import send_digests
from app.services.insights import sync_tasks
from app.services.reminders import generate_reminders

logger = logging.getLogger(__name__)


def run_scheduled(db: Session, company_ids: set[uuid.UUID] | None = None) -> dict[str, int]:
    statement = select(Company).where(Company.status == "active", Company.setup_completed_at.is_not(None))
    if company_ids is not None:
        statement = statement.where(Company.id.in_(company_ids))
    companies = list(db.scalars(statement))
    totals = {"companies": 0, "created": 0, "resolved": 0, "members": 0, "digests": 0}
    for company in companies:
        rows = db.execute(
            select(User, CompanyMembership.role)
            .join(CompanyMembership, CompanyMembership.user_id == User.id)
            .where(CompanyMembership.company_id == company.id, CompanyMembership.status == "active")
        ).all()
        owner = next((Member(user=user, company=company, role=role) for user, role in rows if role == "owner"), None)
        try:
            if owner is not None:
                result = sync_tasks(db, owner)
                totals["created"] += result["created"]
                totals["resolved"] += result["resolved"]
            for user, role in rows:
                generate_reminders(db, Member(user=user, company=company, role=role))
                totals["members"] += 1
            totals["digests"] += send_digests(db, company, [(user, role) for user, role in rows])
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Scheduled run failed for company %s", company.id)
            continue
        totals["companies"] += 1
    return totals
