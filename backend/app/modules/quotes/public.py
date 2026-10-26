"""Customer-facing quote page reached through the link in the quote e-mail. No session is involved."""

from datetime import UTC, date, datetime

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.core.security import hash_secret
from app.models.identity import AuditLog, Company, CompanyMembership, User
from app.modules.customers.models import Customer
from app.modules.inventory.models import Product
from app.modules.inventory.service import quantity_text
from app.modules.quotes.models import Quote, QuoteItem
from app.modules.quotes.schemas import DecisionInput, PublicLine, PublicQuote
from app.modules.quotes.service import QuoteError, emit_status, quote_code
from app.modules.sales.service import money_text
from app.services.auth import Member
from app.services.digest import money
from app.services.notifications import notify

INVALID = "Teklif bağlantısı geçersiz veya yenilenmiş. Güncel bağlantı için firmayla iletişime geçin."


def _find(db: Session, raw: str, *, lock: bool = False) -> tuple[Quote, Company, Customer]:
    statement = select(Quote).where(Quote.share_token_hash == hash_secret(raw))
    quote = db.scalar(statement.with_for_update() if lock else statement)
    company = db.get(Company, quote.company_id) if quote else None
    customer = db.get(Customer, quote.customer_id) if quote else None
    if quote is None or company is None or customer is None or company.status != "active":
        raise QuoteError(404, INVALID)
    return quote, company, customer


def _today(db: Session, company: Company) -> date:
    return db.scalar(select(cast(func.timezone(company.timezone, func.now()), Date)))


def _view(db: Session, quote: Quote, company: Company, customer: Customer) -> PublicQuote:
    expired = quote.valid_until is not None and quote.valid_until < _today(db, company)
    lines = db.execute(
        select(QuoteItem, Product.unit).outerjoin(Product, Product.id == QuoteItem.product_id).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.position)
    ).all()
    return PublicQuote(
        company_name=company.name,
        code=quote_code(quote.number),
        customer_name=customer.name,
        status=quote.status,  # type: ignore[arg-type]
        expired=expired,
        can_decide=quote.status == "sent" and not expired,
        currency=quote.currency,  # type: ignore[arg-type]
        quote_date=quote.quote_date,
        valid_until=quote.valid_until,
        note=quote.note,
        subtotal=money_text(quote.subtotal),
        discount_total=money_text(quote.discount_total),
        vat_total=money_text(quote.vat_total),
        total=money_text(quote.total),
        decided_at=quote.decided_at,
        decided_by=quote.decided_by,  # type: ignore[arg-type]
        customer_note=quote.customer_note,
        items=[
            PublicLine(
                description=item.description,
                quantity=quantity_text(item.quantity),
                unit=unit,
                unit_price=money_text(item.unit_price),
                vat_rate=item.vat_rate,
                discount_rate=quantity_text(item.discount_rate),
                line_total=money_text(item.line_total),
            )
            for item, unit in lines
        ],
    )


def view_quote(db: Session, raw: str) -> PublicQuote:
    return _view(db, *_find(db, raw))


def decide_quote(db: Session, raw: str, data: DecisionInput) -> PublicQuote:
    quote, company, customer = _find(db, raw, lock=True)
    target = "accepted" if data.decision == "accept" else "rejected"
    if quote.status == target and quote.decided_by == "customer":
        return _view(db, quote, company, customer)
    if quote.status != "sent":
        raise QuoteError(409, "Bu teklif için karar zaten verilmiş. Bir değişiklik isterseniz firmayla iletişime geçin.")
    if quote.valid_until is not None and quote.valid_until < _today(db, company):
        raise QuoteError(409, "Teklifin geçerlilik süresi dolmuş. Güncel teklif için firmayla iletişime geçin.")

    now = datetime.now(UTC)
    quote.status = target
    quote.decided_at = now
    quote.decided_by = "customer"
    quote.customer_note = data.note
    quote.updated_at = now
    code = quote_code(quote.number)
    db.add(
        AuditLog(
            company_id=company.id,
            action=f"quote.{target}_by_customer",
            entity_type="quote",
            entity_id=str(quote.id),
            summary={"number": quote.number, "customer": customer.name, **({"note": data.note} if data.note else {})},
            source="customer",
        )
    )
    owner = db.get(User, company.owner_user_id)
    if owner is not None:
        member = Member(user=owner, company=company, role="owner")
        emit_status(db, member, quote)
        recipients = set(
            db.scalars(
                select(CompanyMembership.user_id).where(
                    CompanyMembership.company_id == company.id, CompanyMembership.status == "active", CompanyMembership.role.in_(("owner", "admin"))
                )
            )
        )
        if quote.created_by is not None:
            recipients.add(quote.created_by)
        verb = "kabul etti" if target == "accepted" else "reddetti"
        body = f"Tutar {money(quote.total, quote.currency)}."
        if data.note:
            body += f" Müşterinin notu: “{data.note}”"
        if target == "accepted":
            body += " Teklifi siparişe çevirebilirsiniz."
        for user_id in sorted(recipients, key=str):
            notify(
                db,
                member,
                category="quotes",
                title=f"{customer.name}, {code} teklifini {verb}.",
                body=body[:400],
                link=f"/panel/musteriler?bolum=teklifler&teklif={quote.id}",
                dedupe_key=f"quote.decision:{quote.id}",
                user_id=user_id,
            )
    db.commit()
    return _view(db, quote, company, customer)
