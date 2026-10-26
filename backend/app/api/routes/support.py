from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import current_member, require_csrf
from app.core.database import get_db
from app.schemas.support import MessageCreate, TicketCreate, TicketDetail, TicketList
from app.services import support
from app.services.auth import Member

router = APIRouter(prefix="/support/tickets")


def _setup_member(member: Member = Depends(current_member)) -> Member:
    if member.company.setup_completed_at is None:
        raise HTTPException(status_code=403, detail="Önce çalışma alanı kurulumunu tamamlayın.")
    return member


def _run(action):  # type: ignore[no-untyped-def]
    try:
        return action()
    except support.SupportError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None


@router.get("", response_model=TicketList)
def read_tickets(db: Session = Depends(get_db), member: Member = Depends(_setup_member)) -> TicketList:
    return support.list_tickets(db, member)


@router.post("", response_model=TicketDetail, status_code=201)
def open_ticket(
    payload: TicketCreate,
    db: Session = Depends(get_db),
    member: Member = Depends(_setup_member),
    _: None = Depends(require_csrf),
) -> TicketDetail:
    return _run(lambda: support.create_ticket(db, member, payload))


@router.get("/{ticket_id}", response_model=TicketDetail)
def read_ticket(ticket_id: UUID, db: Session = Depends(get_db), member: Member = Depends(_setup_member)) -> TicketDetail:
    return _run(lambda: support.get_ticket(db, member, ticket_id))


@router.post("/{ticket_id}/messages", response_model=TicketDetail)
def write_message(
    ticket_id: UUID,
    payload: MessageCreate,
    db: Session = Depends(get_db),
    member: Member = Depends(_setup_member),
    _: None = Depends(require_csrf),
) -> TicketDetail:
    return _run(lambda: support.add_message(db, member, ticket_id, payload))


@router.post("/{ticket_id}/close", response_model=TicketDetail)
def close(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    member: Member = Depends(_setup_member),
    _: None = Depends(require_csrf),
) -> TicketDetail:
    return _run(lambda: support.close_ticket(db, member, ticket_id))
