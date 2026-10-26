from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import require_csrf
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import SESSION_COOKIE
from app.schemas.account import AdminClosure
from app.schemas.mail import MailItem, MailList
from app.schemas.support import (
    AdminCompanyDetail,
    AdminCompanyList,
    AdminOverview,
    CompanyDeletion,
    MessageCreate,
    StaffMessage,
    TicketDetail,
    TicketList,
)
from app.services import account, admin, mail, support
from app.services.auth import AuthError, Member, resolve_staff

router = APIRouter(prefix="/admin")


def platform_admin(request: Request, db: Session = Depends(get_db)) -> Member:
    """Platform staff, whether or not they also belong to a workspace. company is None for the staff-only account."""
    try:
        user = resolve_staff(db, request.cookies.get(SESSION_COOKIE))
    except AuthError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None
    return Member(user=user, company=None, role="staff")  # type: ignore[arg-type]


@router.get("/companies/{company_id}", response_model=AdminCompanyDetail)
def read_company(company_id: UUID, db: Session = Depends(get_db), _: Member = Depends(platform_admin)) -> AdminCompanyDetail:
    return _run(lambda: admin.company_detail(db, company_id))


@router.post("/companies/{company_id}/messages", response_model=TicketDetail, status_code=201)
def message_company(
    company_id: UUID,
    payload: StaffMessage,
    db: Session = Depends(get_db),
    staff: Member = Depends(platform_admin),
    _: None = Depends(require_csrf),
) -> TicketDetail:
    return _run(lambda: admin.message_company(db, staff, company_id, payload))


@router.delete("/companies/{company_id}", status_code=204)
def delete_company(
    company_id: UUID,
    payload: CompanyDeletion,
    db: Session = Depends(get_db),
    staff: Member = Depends(platform_admin),
    _: None = Depends(require_csrf),
) -> Response:
    _run(lambda: admin.delete_company(db, staff, company_id, payload.confirm_name))
    return Response(status_code=204)


def _run(action):  # type: ignore[no-untyped-def]
    try:
        return action()
    except support.SupportError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None


@router.get("/overview", response_model=AdminOverview)
def read_overview(db: Session = Depends(get_db), _: Member = Depends(platform_admin)) -> AdminOverview:
    return support.overview(db)


@router.get("/companies", response_model=AdminCompanyList)
def read_companies(
    q: str | None = Query(default=None, max_length=80),
    page: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
    _: Member = Depends(platform_admin),
) -> AdminCompanyList:
    return support.companies(db, q, page)


@router.get("/closures", response_model=list[AdminClosure])
def read_closures(db: Session = Depends(get_db), _: Member = Depends(platform_admin)) -> list[AdminClosure]:
    return [AdminClosure.model_validate(row) for row in account.list_closures(db)]


@router.post("/closures/{request_id}/complete", status_code=204)
def complete_closure(
    request_id: UUID,
    db: Session = Depends(get_db),
    staff: Member = Depends(platform_admin),
    _: None = Depends(require_csrf),
) -> Response:
    try:
        account.complete_closure(db, staff, request_id)
    except account.AccountError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None
    return Response(status_code=204)


def _mail_item(message, company_name: str | None) -> MailItem:  # type: ignore[no-untyped-def]
    return MailItem(
        id=message.id,
        kind=message.kind,
        kind_label=mail.KIND_LABELS.get(message.kind, message.kind),
        to_email=message.to_email,
        subject=message.subject,
        company_name=company_name,
        status=message.status,
        attempts=message.attempts,
        last_error=message.last_error,
        provider_message_id=message.provider_message_id,
        retryable=message.status == "failed" and message.body_text is not None,
        created_at=message.created_at,
        handed_off_at=message.handed_off_at,
        sent_at=message.sent_at,
    )


@router.get("/mail", response_model=MailList)
def read_mail(
    status: Literal["queued", "handed_off", "sent", "failed"] | None = Query(default=None),
    db: Session = Depends(get_db),
    _: Member = Depends(platform_admin),
) -> MailList:
    rows, counts = mail.list_messages(db, status)
    url = get_settings().mail_webhook_url
    return MailList(
        configured=mail.configured(),
        webhook_host=urlsplit(url).netloc or None if url else None,
        counts=counts,
        items=[_mail_item(message, name) for message, name in rows],
    )


@router.post("/mail/{message_id}/retry", response_model=MailItem)
def retry_mail(
    message_id: UUID,
    db: Session = Depends(get_db),
    _: Member = Depends(platform_admin),
    __: None = Depends(require_csrf),
) -> MailItem:
    try:
        message = mail.retry(db, message_id)
    except mail.MailError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None
    return _mail_item(message, None)


@router.get("/support/tickets", response_model=TicketList)
def read_tickets(
    status: Literal["open", "answered", "closed"] | None = Query(default=None),
    db: Session = Depends(get_db),
    _: Member = Depends(platform_admin),
) -> TicketList:
    return support.staff_tickets(db, status)


@router.get("/support/tickets/{ticket_id}", response_model=TicketDetail)
def read_ticket(ticket_id: UUID, db: Session = Depends(get_db), _: Member = Depends(platform_admin)) -> TicketDetail:
    return _run(lambda: support.staff_ticket(db, ticket_id))


@router.post("/support/tickets/{ticket_id}/reply", response_model=TicketDetail)
def reply(
    ticket_id: UUID,
    payload: MessageCreate,
    db: Session = Depends(get_db),
    staff: Member = Depends(platform_admin),
    _: None = Depends(require_csrf),
) -> TicketDetail:
    return _run(lambda: support.staff_reply(db, staff, ticket_id, payload))


@router.post("/support/tickets/{ticket_id}/close", response_model=TicketDetail)
def close(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    staff: Member = Depends(platform_admin),
    _: None = Depends(require_csrf),
) -> TicketDetail:
    return _run(lambda: support.staff_close(db, staff, ticket_id))
