from collections.abc import Callable
from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.api.deps import require_csrf, require_module
from app.core.database import get_db
from app.modules.quotes.public import decide_quote, view_quote
from app.modules.quotes.schemas import DecisionInput, PublicQuote, QuoteDetail, QuoteInput, QuotePage, QuoteSort, QuoteStatus, QuoteSummary, SendInput
from app.modules.quotes.service import (
    QuoteError,
    convert_quote,
    create_quote,
    get_quote,
    list_quotes,
    quote_summary,
    resend_quote,
    transition_quote,
    update_quote,
)
from app.services.auth import Member

router = APIRouter(prefix="/quotes")
quotes_member = require_module("customers")


def _raise(error: QuoteError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.detail)


@router.get("/summary", response_model=QuoteSummary)
def read_summary(db: Session = Depends(get_db), member: Member = Depends(quotes_member)) -> QuoteSummary:
    return quote_summary(db, member)


@router.get("", response_model=QuotePage)
def read_quotes(
    q: str | None = Query(default=None, max_length=120),
    status: QuoteStatus | None = None,
    sort: QuoteSort = "-created_at",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    member: Member = Depends(quotes_member),
) -> QuotePage:
    return list_quotes(db, member, query=q, status=status, sort=sort, page=page, page_size=page_size)


@router.post("", response_model=QuoteDetail, status_code=201)
def add_quote(payload: QuoteInput, db: Session = Depends(get_db), member: Member = Depends(quotes_member), _: None = Depends(require_csrf)) -> QuoteDetail:
    try:
        return create_quote(db, member, payload)
    except QuoteError as error:
        _raise(error)


@router.get("/{quote_id}", response_model=QuoteDetail)
def read_quote(quote_id: UUID, db: Session = Depends(get_db), member: Member = Depends(quotes_member)) -> QuoteDetail:
    try:
        return get_quote(db, member, quote_id)
    except QuoteError as error:
        _raise(error)


@router.put("/{quote_id}", response_model=QuoteDetail)
def change_quote(
    quote_id: UUID, payload: QuoteInput, db: Session = Depends(get_db), member: Member = Depends(quotes_member), _: None = Depends(require_csrf)
) -> QuoteDetail:
    try:
        return update_quote(db, member, quote_id, payload)
    except QuoteError as error:
        _raise(error)


def _action(run: Callable[[Session, Member, UUID], QuoteDetail]):
    def handler(quote_id: UUID, db: Session = Depends(get_db), member: Member = Depends(quotes_member), _: None = Depends(require_csrf)) -> QuoteDetail:
        try:
            return run(db, member, quote_id)
        except QuoteError as error:
            _raise(error)

    return handler


for name in ("accept", "reject"):
    router.add_api_route(
        f"/{{quote_id}}/{name}",
        _action(lambda db, member, quote_id, name=name: transition_quote(db, member, quote_id, name)),
        methods=["POST"],
        response_model=QuoteDetail,
    )
router.add_api_route("/{quote_id}/convert", _action(convert_quote), methods=["POST"], response_model=QuoteDetail)


@router.post("/{quote_id}/send", response_model=QuoteDetail)
def send(
    quote_id: UUID,
    payload: SendInput | None = None,
    db: Session = Depends(get_db),
    member: Member = Depends(quotes_member),
    _: None = Depends(require_csrf),
) -> QuoteDetail:
    try:
        return transition_quote(db, member, quote_id, "send", payload)
    except QuoteError as error:
        _raise(error)


@router.post("/{quote_id}/resend", response_model=QuoteDetail)
def resend(
    quote_id: UUID,
    payload: SendInput,
    db: Session = Depends(get_db),
    member: Member = Depends(quotes_member),
    _: None = Depends(require_csrf),
) -> QuoteDetail:
    try:
        return resend_quote(db, member, quote_id, payload)
    except QuoteError as error:
        _raise(error)


public = APIRouter(prefix="/public/quotes")
TOKEN = Path(min_length=20, max_length=200)


@public.get("/{token}", response_model=PublicQuote)
def read_public(token: str = TOKEN, db: Session = Depends(get_db)) -> PublicQuote:
    try:
        return view_quote(db, token)
    except QuoteError as error:
        _raise(error)


@public.post("/{token}/decision", response_model=PublicQuote)
def decide(payload: DecisionInput, token: str = TOKEN, db: Session = Depends(get_db), _: None = Depends(require_csrf)) -> PublicQuote:
    try:
        return decide_quote(db, token, payload)
    except QuoteError as error:
        _raise(error)
