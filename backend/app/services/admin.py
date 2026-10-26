"""Platform staff actions on companies: profile without business data, messages, deletion."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.identity import AuditLog, Company, CompanyMembership, LoginAttempt, User
from app.models.modules import CompanyModule
from app.models.support import SupportMessage, SupportTicket
from app.models.team import CompanyInvitation, JoinRequest
from app.modules.catalog import MODULES
from app.schemas.support import AdminCompanyDetail, AdminModule, AdminPerson, StaffMessage, TicketDetail
from app.services.auth import Member
from app.services.notifications import notify
from app.services.support import STAFF_NAME, SupportError, _detail, _name, companies

ROLE_ORDER = {"owner": 0, "admin": 1, "member": 2}


def _company(db: Session, company_id: uuid.UUID) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise SupportError(404, "Şirket bulunamadı.")
    return company


def company_detail(db: Session, company_id: uuid.UUID) -> AdminCompanyDetail:
    """Who works there and which modules they use. Records inside the modules are not shown."""
    company = _company(db, company_id)
    summary = next(item for item in companies(db, None, 1, page_size=10_000).items if item.id == company.id)
    modules = db.scalars(select(CompanyModule).where(CompanyModule.company_id == company.id, CompanyModule.status == "enabled")).all()
    people = db.execute(
        select(User, CompanyMembership)
        .join(CompanyMembership, CompanyMembership.user_id == User.id)
        .where(CompanyMembership.company_id == company.id, CompanyMembership.status == "active")
    ).all()
    pending_requests = db.scalar(select(func.count()).select_from(JoinRequest).where(JoinRequest.company_id == company.id, JoinRequest.status == "pending"))
    pending_invites = db.scalar(
        select(func.count())
        .select_from(CompanyInvitation)
        .where(CompanyInvitation.company_id == company.id, CompanyInvitation.accepted_at.is_(None), CompanyInvitation.revoked_at.is_(None))
    )
    return AdminCompanyDetail(
        **summary.model_dump(),
        sector=company.sector,
        team_size=company.team_size,
        module_list=[AdminModule(key=row.module_key, name=MODULES[row.module_key].name, enabled_at=row.enabled_at) for row in modules if row.module_key in MODULES],
        people=sorted(
            (AdminPerson(name=_name(user), email=user.email, role=membership.role, joined_at=membership.created_at) for user, membership in people),
            key=lambda person: (ROLE_ORDER.get(person.role, 9), person.name),
        ),
        pending_join_requests=int(pending_requests or 0),
        pending_invitations=int(pending_invites or 0),
    )


def message_company(db: Session, staff: Member, company_id: uuid.UUID, data: StaffMessage) -> TicketDetail:
    """Starts a support conversation from the LUMINOVA side; the company's managers are notified and can reply."""
    company = _company(db, company_id)
    if company.status != "active":
        raise SupportError(409, "Kapalı bir şirkete mesaj gönderilemez.")
    db.execute(select(Company.id).where(Company.id == company.id).with_for_update())
    last = db.scalar(select(func.max(SupportTicket.number)).where(SupportTicket.company_id == company.id)) or 0
    now = datetime.now(UTC)
    ticket = SupportTicket(
        id=uuid.uuid4(),
        company_id=company.id,
        number=int(last) + 1,
        created_by=company.owner_user_id,
        subject=data.subject,
        category="notice",
        status="answered",
        opened_by_staff=True,
        created_at=now,
        updated_at=now,
    )
    db.add(ticket)
    db.flush()
    db.add(SupportMessage(ticket_id=ticket.id, company_id=company.id, author_user_id=staff.user.id, author_kind="staff", body=data.body, created_at=now))
    db.add(
        AuditLog(
            company_id=company.id,
            actor_user_id=staff.user.id,
            action="admin.message_sent",
            entity_type="support_ticket",
            entity_id=str(ticket.id),
            summary={"number": ticket.number},
            source="admin",
        )
    )
    managers = db.scalars(
        select(CompanyMembership.user_id).where(
            CompanyMembership.company_id == company.id, CompanyMembership.status == "active", CompanyMembership.role.in_(("owner", "admin"))
        )
    )
    for user_id in managers:
        notify(
            db,
            staff,
            category="support",
            title=f"{STAFF_NAME} size mesaj gönderdi: {data.subject}"[:160],
            body=data.body[:400],
            link=f"/panel/destek?talep={ticket.id}",
            dedupe_key=f"support.staff_message:{ticket.id}",
            user_id=user_id,
            company_id=company.id,
        )
    db.commit()
    return _detail(db, ticket, staff=True)


def _user_columns() -> list[tuple[object, object]]:
    """(table, column) pairs that point at users.id, children first."""
    found = []
    for table in reversed(Base.metadata.sorted_tables):
        for column in table.columns:
            if any(key.column.table.name == "users" and key.column.name == "id" for key in column.foreign_keys):
                found.append((table, column))
    return found


def delete_company(db: Session, staff: Member, company_id: uuid.UUID, confirm_name: str) -> None:
    """Removes the company and every row that belongs to it, plus accounts that belonged only to it."""
    company = _company(db, company_id)
    if confirm_name.strip() != company.name:
        raise SupportError(422, "Silmek için şirket adını tam olarak yazın.")
    name, slug = company.name, company.slug
    members = set(db.scalars(select(CompanyMembership.user_id).where(CompanyMembership.company_id == company.id)))
    members |= set(db.scalars(select(JoinRequest.user_id).where(JoinRequest.company_id == company.id)))
    elsewhere = set(db.scalars(select(CompanyMembership.user_id).where(CompanyMembership.user_id.in_(members), CompanyMembership.company_id != company.id)))
    staff_ids = set(db.scalars(select(User.id).where(User.id.in_(members), User.is_platform_admin.is_(True))))
    accounts = members - elsewhere - staff_ids

    for table in reversed(Base.metadata.sorted_tables):
        if table.name == "companies":
            continue
        if "company_id" in table.columns:
            db.execute(delete(table).where(table.c.company_id == company.id))
            continue
        for column in table.columns:
            for key in column.foreign_keys:
                parent = key.column.table
                if parent.name == "companies":
                    db.execute(delete(table).where(column == company.id))
                elif "company_id" in parent.columns:
                    db.execute(delete(table).where(column.in_(select(key.column).where(parent.c.company_id == company.id))))
    db.execute(delete(Company.__table__).where(Company.__table__.c.id == company.id))

    if accounts:
        emails = list(db.scalars(select(User.email).where(User.id.in_(accounts))))
        for table, column in _user_columns():
            if table.name == "users":
                continue
            if column.nullable:  # type: ignore[attr-defined]
                db.execute(update(table).where(column.in_(accounts)).values({column.name: None}))  # type: ignore[attr-defined]
            else:
                db.execute(delete(table).where(column.in_(accounts)))  # type: ignore[attr-defined]
        db.execute(delete(LoginAttempt).where(LoginAttempt.email.in_(emails)))
        db.execute(delete(User).where(User.id.in_(accounts)))

    db.add(
        AuditLog(
            company_id=None,
            actor_user_id=staff.user.id,
            action="admin.company_deleted",
            entity_type="company",
            entity_id=str(company_id),
            summary={"name": name, "slug": slug, "accounts_removed": len(accounts)},
            source="admin",
        )
    )
    db.commit()
