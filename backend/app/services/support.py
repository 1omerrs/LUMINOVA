"""Support tickets: company members write, platform staff answer.

Staff functions deliberately read across companies; every other query is
scoped to the caller's company.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.closure import ClosureRequest
from app.models.identity import AuditLog, Company, CompanyMembership, User
from app.models.modules import CompanyModule
from app.models.support import SupportMessage, SupportTicket
from app.schemas.support import (
    AdminCompany,
    AdminCompanyList,
    AdminOverview,
    MessageCreate,
    SupportMessageItem,
    TicketCreate,
    TicketDetail,
    TicketItem,
    TicketList,
)
from app.services.auth import Member
from app.services.notifications import notify

OPEN_LIMIT = 20
STAFF_NAME = "LUMINOVA Destek"
STATUS_LABELS = {"open": "yanıt bekliyor", "answered": "yanıtlandı", "closed": "kapandı"}


class SupportError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


def ticket_code(number: int) -> str:
    return f"DT-{number:04d}"


def _name(user: User | None) -> str:
    return f"{user.first_name} {user.last_name}".strip() if user else "Silinmiş kullanıcı"


def _manager(member: Member) -> bool:
    return member.role in {"owner", "admin"}


def _audit(actor: Member, company_id: uuid.UUID, action: str, ticket: SupportTicket, source: str = "api") -> AuditLog:
    return AuditLog(
        company_id=company_id,
        actor_user_id=actor.user.id,
        action=action,
        entity_type="support_ticket",
        entity_id=str(ticket.id),
        summary={"number": ticket.number},
        source=source,
    )


def _stats() -> Select[tuple[uuid.UUID, int, datetime]]:
    return select(SupportMessage.ticket_id, func.count().label("message_count"), func.max(SupportMessage.created_at).label("last_message_at")).group_by(
        SupportMessage.ticket_id
    )


def _items(db: Session, tickets: list[SupportTicket], *, staff: bool) -> list[TicketItem]:
    if not tickets:
        return []
    ids = [ticket.id for ticket in tickets]
    stats = {row[0]: (int(row[1]), row[2]) for row in db.execute(_stats().where(SupportMessage.ticket_id.in_(ids)))}
    users = {user.id: user for user in db.scalars(select(User).where(User.id.in_({ticket.created_by for ticket in tickets})))}
    companies = {company.id: company.name for company in db.scalars(select(Company).where(Company.id.in_({ticket.company_id for ticket in tickets})))} if staff else {}
    return [
        TicketItem(
            id=ticket.id,
            code=ticket_code(ticket.number),
            subject=ticket.subject,
            category=ticket.category,  # type: ignore[arg-type]
            status=ticket.status,  # type: ignore[arg-type]
            created_by_name=STAFF_NAME if ticket.opened_by_staff else _name(users.get(ticket.created_by)),
            opened_by_staff=ticket.opened_by_staff,
            message_count=stats.get(ticket.id, (0, ticket.created_at))[0],
            last_message_at=stats.get(ticket.id, (0, ticket.created_at))[1],
            created_at=ticket.created_at,
            company_id=ticket.company_id if staff else None,
            company_name=companies.get(ticket.company_id) if staff else None,
        )
        for ticket in tickets
    ]


def _counts(db: Session, *conditions: object) -> dict[str, int]:
    rows = db.execute(select(SupportTicket.status, func.count()).where(*conditions).group_by(SupportTicket.status))  # type: ignore[arg-type]
    found = {status: int(count) for status, count in rows}
    return {status: found.get(status, 0) for status in ("open", "answered", "closed")}


def _detail(db: Session, ticket: SupportTicket, *, staff: bool) -> TicketDetail:
    messages = db.scalars(select(SupportMessage).where(SupportMessage.ticket_id == ticket.id).order_by(SupportMessage.created_at, SupportMessage.id)).all()
    authors = {user.id: user for user in db.scalars(select(User).where(User.id.in_({message.author_user_id for message in messages})))} if messages else {}
    item = _items(db, [ticket], staff=staff)[0]
    return TicketDetail(
        **item.model_dump(),
        messages=[
            SupportMessageItem(
                id=message.id,
                author_kind=message.author_kind,  # type: ignore[arg-type]
                author_name=(f"{STAFF_NAME} · {_name(authors.get(message.author_user_id))}" if staff else STAFF_NAME)
                if message.author_kind == "staff"
                else _name(authors.get(message.author_user_id)),
                body=message.body,
                created_at=message.created_at,
            )
            for message in messages
        ],
        can_reply=ticket.status != "closed",
    )


def _scope(member: Member) -> list[object]:
    conditions: list[object] = [SupportTicket.company_id == member.company.id]
    if not _manager(member):
        conditions.append(SupportTicket.created_by == member.user.id)
    return conditions


def _owned(db: Session, member: Member, ticket_id: uuid.UUID, *, lock: bool = False) -> SupportTicket:
    statement = select(SupportTicket).where(SupportTicket.id == ticket_id, *_scope(member))  # type: ignore[arg-type]
    ticket = db.scalar(statement.with_for_update() if lock else statement)
    if ticket is None:
        raise SupportError(404, "Destek talebi bulunamadı.")
    return ticket


def list_tickets(db: Session, member: Member) -> TicketList:
    scope = _scope(member)
    tickets = db.scalars(select(SupportTicket).where(*scope).order_by(SupportTicket.updated_at.desc()).limit(100)).all()  # type: ignore[arg-type]
    return TicketList(items=_items(db, list(tickets), staff=False), **_counts(db, *scope))


def create_ticket(db: Session, member: Member, data: TicketCreate) -> TicketDetail:
    db.execute(select(Company.id).where(Company.id == member.company.id).with_for_update())
    waiting = db.scalar(
        select(func.count()).select_from(SupportTicket).where(SupportTicket.created_by == member.user.id, SupportTicket.status != "closed")
    )
    if int(waiting or 0) >= OPEN_LIMIT:
        raise SupportError(409, f"Aynı anda en çok {OPEN_LIMIT} açık talebiniz olabilir. Çözülenleri kapatıp yeniden deneyin.")
    last = db.scalar(select(func.max(SupportTicket.number)).where(SupportTicket.company_id == member.company.id)) or 0
    now = datetime.now(UTC)
    ticket = SupportTicket(
        id=uuid.uuid4(),
        company_id=member.company.id,
        number=int(last) + 1,
        created_by=member.user.id,
        subject=data.subject,
        category=data.category,
        status="open",
        created_at=now,
        updated_at=now,
    )
    db.add(ticket)
    db.flush()
    db.add(SupportMessage(ticket_id=ticket.id, company_id=member.company.id, author_user_id=member.user.id, author_kind="customer", body=data.body, created_at=now))
    db.add(_audit(member, member.company.id, "support.ticket_created", ticket))
    db.commit()
    return _detail(db, ticket, staff=False)


def get_ticket(db: Session, member: Member, ticket_id: uuid.UUID) -> TicketDetail:
    return _detail(db, _owned(db, member, ticket_id), staff=False)


def add_message(db: Session, member: Member, ticket_id: uuid.UUID, data: MessageCreate) -> TicketDetail:
    ticket = _owned(db, member, ticket_id, lock=True)
    if ticket.status == "closed":
        raise SupportError(409, "Kapanan talebe yanıt yazılamaz. Gerekirse yeni bir talep açın.")
    now = datetime.now(UTC)
    db.add(SupportMessage(ticket_id=ticket.id, company_id=ticket.company_id, author_user_id=member.user.id, author_kind="customer", body=data.body, created_at=now))
    ticket.status = "open"
    ticket.updated_at = now
    db.add(_audit(member, ticket.company_id, "support.message_added", ticket))
    db.commit()
    return _detail(db, ticket, staff=False)


def close_ticket(db: Session, member: Member, ticket_id: uuid.UUID) -> TicketDetail:
    ticket = _owned(db, member, ticket_id, lock=True)
    if ticket.status != "closed":
        now = datetime.now(UTC)
        ticket.status = "closed"
        ticket.closed_at = now
        ticket.updated_at = now
        db.add(_audit(member, ticket.company_id, "support.ticket_closed", ticket))
        db.commit()
    return _detail(db, ticket, staff=False)


def staff_tickets(db: Session, status: str | None) -> TicketList:
    conditions: list[object] = [] if status is None else [SupportTicket.status == status]
    order = (SupportTicket.updated_at.asc(),) if status == "open" else (SupportTicket.updated_at.desc(),)
    tickets = db.scalars(select(SupportTicket).where(*conditions).order_by(*order).limit(200)).all()  # type: ignore[arg-type]
    return TicketList(items=_items(db, list(tickets), staff=True), **_counts(db))


def _staff_ticket(db: Session, ticket_id: uuid.UUID, *, lock: bool = False) -> SupportTicket:
    statement = select(SupportTicket).where(SupportTicket.id == ticket_id)
    ticket = db.scalar(statement.with_for_update() if lock else statement)
    if ticket is None:
        raise SupportError(404, "Destek talebi bulunamadı.")
    return ticket


def staff_ticket(db: Session, ticket_id: uuid.UUID) -> TicketDetail:
    return _detail(db, _staff_ticket(db, ticket_id), staff=True)


def staff_reply(db: Session, staff: Member, ticket_id: uuid.UUID, data: MessageCreate) -> TicketDetail:
    ticket = _staff_ticket(db, ticket_id, lock=True)
    if ticket.status == "closed":
        raise SupportError(409, "Kapanan talebe yanıt yazılamaz.")
    now = datetime.now(UTC)
    db.add(SupportMessage(ticket_id=ticket.id, company_id=ticket.company_id, author_user_id=staff.user.id, author_kind="staff", body=data.body, created_at=now))
    ticket.status = "answered"
    ticket.updated_at = now
    db.add(_audit(staff, ticket.company_id, "admin.support_replied", ticket, source="admin"))
    notify(
        db,
        staff,
        category="support",
        title=f"{ticket_code(ticket.number)} talebinize yanıt geldi.",
        body=ticket.subject[:200],
        link=f"/panel/destek?talep={ticket.id}",
        user_id=ticket.created_by,
        company_id=ticket.company_id,
    )
    db.commit()
    return _detail(db, ticket, staff=True)


def staff_close(db: Session, staff: Member, ticket_id: uuid.UUID) -> TicketDetail:
    ticket = _staff_ticket(db, ticket_id, lock=True)
    if ticket.status != "closed":
        now = datetime.now(UTC)
        ticket.status = "closed"
        ticket.closed_at = now
        ticket.updated_at = now
        db.add(_audit(staff, ticket.company_id, "admin.support_closed", ticket, source="admin"))
        db.commit()
    return _detail(db, ticket, staff=True)


def overview(db: Session) -> AdminOverview:
    since = datetime.now(UTC) - timedelta(days=30)
    counts = _counts(db)
    return AdminOverview(
        companies=int(db.scalar(select(func.count()).select_from(Company)) or 0),
        active_companies=int(db.scalar(select(func.count()).select_from(Company).where(Company.status == "active", Company.setup_completed_at.is_not(None))) or 0),
        setup_pending=int(db.scalar(select(func.count()).select_from(Company).where(Company.setup_completed_at.is_(None))) or 0),
        users=int(db.scalar(select(func.count()).select_from(User).where(User.status == "active")) or 0),
        signups_30d=int(db.scalar(select(func.count()).select_from(User).where(User.created_at >= since)) or 0),
        open_tickets=counts["open"],
        answered_tickets=counts["answered"],
        pending_closures=int(db.scalar(select(func.count()).select_from(ClosureRequest).where(ClosureRequest.status == "pending")) or 0),
    )


def companies(db: Session, q: str | None, page: int, page_size: int = 25) -> AdminCompanyList:
    conditions = []
    if q:
        pattern = f"%{q.strip()}%"
        conditions.append(Company.name.ilike(pattern) | Company.slug.ilike(pattern))
    total = int(db.scalar(select(func.count()).select_from(Company).where(*conditions)) or 0)
    members = (
        select(CompanyMembership.company_id, func.count().label("members"))
        .where(CompanyMembership.status == "active")
        .group_by(CompanyMembership.company_id)
        .subquery()
    )
    modules = (
        select(CompanyModule.company_id, func.count().label("modules")).where(CompanyModule.status == "enabled").group_by(CompanyModule.company_id).subquery()
    )
    activity = select(AuditLog.company_id, func.max(AuditLog.created_at).label("last_at")).group_by(AuditLog.company_id).subquery()
    tickets = (
        select(SupportTicket.company_id, func.count().label("open_tickets")).where(SupportTicket.status == "open").group_by(SupportTicket.company_id).subquery()
    )
    rows = db.execute(
        select(Company, User, members.c.members, modules.c.modules, activity.c.last_at, tickets.c.open_tickets)
        .join(User, User.id == Company.owner_user_id)
        .outerjoin(members, members.c.company_id == Company.id)
        .outerjoin(modules, modules.c.company_id == Company.id)
        .outerjoin(activity, activity.c.company_id == Company.id)
        .outerjoin(tickets, tickets.c.company_id == Company.id)
        .where(*conditions)
        .order_by(Company.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return AdminCompanyList(
        items=[
            AdminCompany(
                id=company.id,
                name=company.name,
                slug=company.slug,
                status=company.status,
                created_at=company.created_at,
                setup_completed=company.setup_completed_at is not None,
                owner_name=_name(owner),
                owner_email=owner.email,
                members=int(member_count or 0),
                modules=int(module_count or 0),
                last_activity_at=last_at,
                open_tickets=int(open_count or 0),
            )
            for company, owner, member_count, module_count, last_at, open_count in rows
        ],
        total=total,
    )
