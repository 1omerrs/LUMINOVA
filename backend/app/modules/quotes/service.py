import re
import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, literal, or_, select
from sqlalchemy.orm import Session

from app.core.security import hash_secret, new_secret
from app.models.identity import AuditLog, Company
from app.modules.customers.models import Customer
from app.modules.inventory.models import Product
from app.modules.inventory.service import WHOLE_UNITS, quantity_label, quantity_text
from app.modules.quotes.models import Quote, QuoteItem
from app.modules.quotes.schemas import QuoteDetail, QuoteInput, QuotePage, QuoteSort, QuoteStatus, QuoteSummary, QuoteSummaryItem, SendInput
from app.modules.sales.models import SalesOrder
from app.modules.sales.schemas import OrderInput, OrderLine, OrderLineInput
from app.modules.sales.service import SalesError, build_order, money_text, order_code, price_line
from app.modules.tasks.service import company_today
from app.services import mail
from app.services.auth import Member
from app.services.automation import emit
from app.services.digest import money
from app.services.modules import can_edit, enabled_keys

CENT = Decimal("0.01")
STATUS_LABELS = {"draft": "taslak", "sent": "gönderildi", "accepted": "kabul edildi", "rejected": "reddedildi"}
_TURKISH = "tr-TR-x-icu"
_CODE = re.compile(r"^(?:tk-?)?0*(\d{1,9})$", re.IGNORECASE)
_ORDER = {
    "-created_at": (Quote.created_at.desc(), Quote.id.desc()),
    "-quote_date": (Quote.quote_date.desc(), Quote.number.desc()),
    "-total": (Quote.total.desc(), Quote.number.desc()),
    "number": (Quote.number.asc(),),
}


class QuoteError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


def quote_code(number: int) -> str:
    return f"TK-{number:04d}"


def list_quotes(db: Session, member: Member, *, query: str | None, status: QuoteStatus | None, sort: QuoteSort, page: int, page_size: int) -> QuotePage:
    today = company_today(db, member)
    filters = [Quote.company_id == member.company.id]
    if status is not None:
        filters.append(Quote.status == status)
    term = (query or "").strip()
    if term:
        code = _CODE.match(term)
        pattern = func.lower(literal(f"%{term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')}%").collate(_TURKISH))
        by_name = func.lower(Customer.name.collate(_TURKISH)).like(pattern, escape="\\")
        filters.append(or_(by_name, Quote.number == int(code.group(1))) if code else by_name)
    counts = select(QuoteItem.quote_id, func.count().label("line_count")).where(QuoteItem.company_id == member.company.id).group_by(QuoteItem.quote_id).subquery()
    rows = db.execute(
        select(Quote, Customer.name, func.coalesce(counts.c.line_count, 0), SalesOrder.number)
        .join(Customer, Customer.id == Quote.customer_id)
        .outerjoin(counts, counts.c.quote_id == Quote.id)
        .outerjoin(SalesOrder, SalesOrder.id == Quote.order_id)
        .where(*filters)
        .order_by(*_ORDER[sort])
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    total = db.scalar(select(func.count()).select_from(Quote).join(Customer, Customer.id == Quote.customer_id).where(*filters)) or 0
    return QuotePage(items=[_summary(quote, name, int(count), number, today) for quote, name, count, number in rows], total=int(total), page=page, page_size=page_size)


def quote_summary(db: Session, member: Member) -> QuoteSummary:
    scope = Quote.company_id == member.company.id
    counts = {status: int(count) for status, count in db.execute(select(Quote.status, func.count()).where(scope).group_by(Quote.status)).all()}
    open_value = db.scalar(select(func.coalesce(func.sum(Quote.total), 0)).where(scope, Quote.status == "sent", Quote.currency == "TRY")) or 0
    return QuoteSummary(
        draft=counts.get("draft", 0),
        sent=counts.get("sent", 0),
        accepted=counts.get("accepted", 0),
        rejected=counts.get("rejected", 0),
        open_value=money_text(Decimal(open_value)),
    )


def get_quote(db: Session, member: Member, quote_id: uuid.UUID) -> QuoteDetail:
    return _detail(db, member, _owned(db, member, quote_id))


def create_quote(db: Session, member: Member, data: QuoteInput) -> QuoteDetail:
    customer = _customer(db, member, data.customer_id)
    db.execute(select(Company.id).where(Company.id == member.company.id).with_for_update())
    last = db.scalar(select(func.max(Quote.number)).where(Quote.company_id == member.company.id)) or 0
    quote = Quote(
        id=uuid.uuid4(),
        company_id=member.company.id,
        number=int(last) + 1,
        customer_id=customer.id,
        currency=data.currency,
        quote_date=data.quote_date,
        valid_until=data.valid_until,
        note=data.note,
        created_by=member.user.id,
    )
    db.add(quote)
    db.flush()
    _replace_lines(db, member, quote, data.items)
    db.add(_audit(member, "quote.created", quote, {"lines": len(data.items)}))
    db.commit()
    return _detail(db, member, quote)


def update_quote(db: Session, member: Member, quote_id: uuid.UUID, data: QuoteInput) -> QuoteDetail:
    quote = _owned(db, member, quote_id, lock=True)
    if quote.status != "draft":
        raise QuoteError(409, "Yalnızca taslak teklifler düzenlenebilir.")
    quote.customer_id = _customer(db, member, data.customer_id).id
    quote.currency = data.currency
    quote.quote_date = data.quote_date
    quote.valid_until = data.valid_until
    quote.note = data.note
    quote.updated_at = datetime.now(UTC)
    for item in db.scalars(select(QuoteItem).where(QuoteItem.quote_id == quote.id)):
        db.delete(item)
    db.flush()
    _replace_lines(db, member, quote, data.items)
    db.add(_audit(member, "quote.updated", quote, {"lines": len(data.items)}))
    db.commit()
    return _detail(db, member, quote)


def transition_quote(db: Session, member: Member, quote_id: uuid.UUID, action: str, options: SendInput | None = None) -> QuoteDetail:
    quote = _owned(db, member, quote_id, lock=True)
    allowed = {"send": ({"draft"}, "sent"), "accept": ({"sent"}, "accepted"), "reject": ({"sent"}, "rejected")}
    sources, target = allowed[action]
    if quote.status not in sources:
        raise QuoteError(409, f"Bu teklif {STATUS_LABELS[quote.status]} durumunda; bu işlem yapılamaz.")
    now = datetime.now(UTC)
    quote.status = target
    quote.updated_at = now
    share_path = notice = None
    if target == "sent":
        quote.sent_at = now
        options = options or SendInput()
        share_path, notice = _share(db, member, quote, options)
        db.add(_audit(member, "quote.sent", quote, {"emailed": _queued(notice)}))
    else:
        quote.decided_at = now
        quote.decided_by = "staff"
        db.add(_audit(member, f"quote.{target}", quote, {}))
    emit_status(db, member, quote)
    db.commit()
    detail = _detail(db, member, quote)
    detail.share_path, detail.email_notice = share_path, notice
    return detail


def resend_quote(db: Session, member: Member, quote_id: uuid.UUID, options: SendInput) -> QuoteDetail:
    """Issues a new customer link (the old one stops working) and e-mails it again if asked."""
    quote = _owned(db, member, quote_id, lock=True)
    if quote.status != "sent":
        raise QuoteError(409, "Yalnızca gönderilmiş ve henüz yanıtlanmamış teklifin bağlantısı yenilenebilir.")
    quote.updated_at = datetime.now(UTC)
    share_path, notice = _share(db, member, quote, options)
    db.add(_audit(member, "quote.resent", quote, {"emailed": _queued(notice)}))
    db.commit()
    detail = _detail(db, member, quote)
    detail.share_path, detail.email_notice = share_path, notice
    return detail


_QUEUED = "gönderim sırasına alındı"


def _queued(notice: str | None) -> bool:
    return bool(notice and _QUEUED in notice)


def _share(db: Session, member: Member, quote: Quote, options: SendInput) -> tuple[str, str | None]:
    raw = new_secret()
    quote.share_token_hash = hash_secret(raw)
    path = f"/teklif/{raw}"
    if not options.email:
        return path, None
    customer = db.get(Customer, quote.customer_id)
    if customer is None or not customer.email:
        return path, "Müşterinin e-posta adresi kayıtlı değil; e-posta gönderilmedi. Bağlantıyı kopyalayıp müşteriye kendiniz iletebilirsiniz."
    if not mail.configured():
        return path, "E-posta servisi yapılandırılmadığı için e-posta gönderilmedi. Bağlantıyı kopyalayıp müşteriye kendiniz iletebilirsiniz."
    lines = db.execute(
        select(QuoteItem, Product.unit).outerjoin(Product, Product.id == QuoteItem.product_id).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.position)
    ).all()
    draft = mail.quote_mail(
        company_name=member.company.name,
        customer_name=customer.name,
        code=quote_code(quote.number),
        lines=[mail.QuoteLine(item.description, f"{quantity_label(item.quantity)} {unit or ''}".strip(), money(item.line_total, quote.currency)) for item, unit in lines],
        total=money(quote.total, quote.currency),
        valid_until=quote.valid_until.strftime("%d.%m.%Y") if quote.valid_until else None,
        message=options.message,
        sender=f"{member.user.first_name} {member.user.last_name}",
        url=mail.absolute(path),
    )
    mail.enqueue(db, kind="quote", to=customer.email, draft=draft, company_id=member.company.id, ref=f"quote:{quote.id}", reply_to=member.user.email)
    return path, f"Teklif e-postası {customer.email} adresine {_QUEUED}."


def emit_status(db: Session, member: Member, quote: Quote) -> None:
    emit(
        db,
        member,
        "quote.status_changed",
        {
            "id": str(quote.id),
            "number": quote_code(quote.number),
            "status": quote.status,
            "decided_by": quote.decided_by,
            "customer_id": str(quote.customer_id),
            "currency": quote.currency,
            "total": f"{quote.total:.2f}",
        },
    )


def convert_quote(db: Session, member: Member, quote_id: uuid.UUID) -> QuoteDetail:
    if "sales" not in enabled_keys(db, member):
        raise QuoteError(403, "Teklifi siparişe çevirmek için Satış ve Siparişler modülünü açın.")
    if not can_edit(db, member, "sales"):
        raise QuoteError(403, "Teklifi siparişe çevirmek için Satış ve Siparişler modülünde düzenleme yetkiniz olmalı.")
    quote = _owned(db, member, quote_id, lock=True)
    if quote.order_id is not None:
        raise QuoteError(409, "Bu teklif zaten siparişe çevrildi.")
    if quote.status != "accepted":
        raise QuoteError(409, "Yalnızca kabul edilen teklif siparişe çevrilebilir.")
    items = db.scalars(select(QuoteItem).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.position)).all()
    code = quote_code(quote.number)
    note = f"{code} teklifinden oluşturuldu." + (f"\n{quote.note}" if quote.note else "")
    order_input = OrderInput(
        customer_id=quote.customer_id,
        currency=quote.currency,
        order_date=company_today(db, member),
        note=note[:1000],
        items=[
            OrderLineInput(
                product_id=item.product_id,
                description="" if item.product_id else item.description,
                quantity=item.quantity.quantize(Decimal("0.001")),
                unit_price=item.unit_price.quantize(CENT),
                vat_rate=item.vat_rate,
                discount_rate=item.discount_rate,
            )
            for item in items
        ],
    )
    try:
        order = build_order(db, member, order_input)
    except SalesError as error:
        db.rollback()
        raise QuoteError(error.status_code, f"Sipariş oluşturulamadı: {error.detail}") from None
    quote.order_id = order.id
    quote.updated_at = datetime.now(UTC)
    db.add(_audit(member, "quote.converted", quote, {"order": order.number}))
    db.commit()
    return _detail(db, member, quote)


def _replace_lines(db: Session, member: Member, quote: Quote, lines: list[OrderLineInput]) -> None:
    product_ids = {line.product_id for line in lines if line.product_id is not None}
    products = (
        {row.id: row for row in db.scalars(select(Product).where(Product.company_id == member.company.id, Product.id.in_(product_ids), Product.deleted_at.is_(None)))}
        if product_ids
        else {}
    )
    subtotal = vat_total = discount_total = Decimal(0)
    for position, line in enumerate(lines, start=1):
        product = products.get(line.product_id) if line.product_id is not None else None
        if line.product_id is not None and product is None:
            raise QuoteError(422, f"{position}. satırdaki ürün bulunamadı.")
        description = line.description or (product.name if product else "")
        if not description:
            raise QuoteError(422, f"{position}. satır için ürün seçin veya açıklama yazın.")
        if product is not None and product.unit in WHOLE_UNITS and line.quantity != line.quantity.to_integral_value():
            raise QuoteError(422, f"{position}. satır: {product.unit.capitalize()} biriminde miktar tam sayı olmalı.")
        line_discount, line_subtotal, line_vat = price_line(line.quantity, line.unit_price, line.discount_rate, line.vat_rate)
        subtotal += line_subtotal
        vat_total += line_vat
        discount_total += line_discount
        db.add(
            QuoteItem(
                company_id=member.company.id,
                quote_id=quote.id,
                position=position,
                product_id=product.id if product else None,
                description=description[:200],
                quantity=line.quantity,
                unit_price=line.unit_price,
                vat_rate=line.vat_rate,
                discount_rate=line.discount_rate,
                line_discount=line_discount,
                line_subtotal=line_subtotal,
                line_vat=line_vat,
                line_total=line_subtotal + line_vat,
            )
        )
    quote.subtotal = subtotal
    quote.discount_total = discount_total
    quote.vat_total = vat_total
    quote.total = subtotal + vat_total


def _customer(db: Session, member: Member, customer_id: uuid.UUID) -> Customer:
    customer = db.scalar(select(Customer).where(Customer.id == customer_id, Customer.company_id == member.company.id, Customer.deleted_at.is_(None)))
    if customer is None:
        raise QuoteError(422, "Seçilen müşteri bulunamadı.")
    return customer


def _owned(db: Session, member: Member, quote_id: uuid.UUID, *, lock: bool = False) -> Quote:
    statement = select(Quote).where(Quote.id == quote_id, Quote.company_id == member.company.id)
    if lock:
        statement = statement.with_for_update()
    quote = db.scalar(statement)
    if quote is None:
        raise QuoteError(404, "Teklif bulunamadı.")
    return quote


def _audit(member: Member, action: str, quote: Quote, summary: dict[str, object]) -> AuditLog:
    return AuditLog(
        company_id=member.company.id,
        actor_user_id=member.user.id,
        action=action,
        entity_type="quote",
        entity_id=str(quote.id),
        summary={"number": quote.number, **summary},
        source="api",
    )


def _summary(quote: Quote, customer_name: str, item_count: int, order_number: int | None, today: date) -> QuoteSummaryItem:
    return QuoteSummaryItem(
        id=quote.id,
        number=quote.number,
        code=quote_code(quote.number),
        customer_id=quote.customer_id,
        customer_name=customer_name,
        status=quote.status,
        expired=quote.status == "sent" and quote.valid_until is not None and quote.valid_until < today,
        currency=quote.currency,
        quote_date=quote.quote_date,
        valid_until=quote.valid_until,
        total=money_text(quote.total),
        item_count=item_count,
        order_id=quote.order_id,
        order_code=order_code(order_number) if order_number else None,
        created_at=quote.created_at,
    )


def _detail(db: Session, member: Member, quote: Quote) -> QuoteDetail:
    db.refresh(quote)
    customer_name, customer_email = db.execute(select(Customer.name, Customer.email).where(Customer.id == quote.customer_id)).one()
    message = mail.latest_status(db, [f"quote:{quote.id}"]).get(f"quote:{quote.id}")
    order_number = db.scalar(select(SalesOrder.number).where(SalesOrder.id == quote.order_id)) if quote.order_id else None
    lines = db.execute(
        select(QuoteItem, Product.sku, Product.unit).outerjoin(Product, Product.id == QuoteItem.product_id).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.position)
    ).all()
    summary = _summary(quote, customer_name, len(lines), order_number, company_today(db, member))
    return QuoteDetail(
        **summary.model_dump(),
        note=quote.note,
        subtotal=money_text(quote.subtotal),
        discount_total=money_text(quote.discount_total),
        vat_total=money_text(quote.vat_total),
        sent_at=quote.sent_at,
        decided_at=quote.decided_at,
        decided_by=quote.decided_by,  # type: ignore[arg-type]
        customer_note=quote.customer_note,
        customer_email=customer_email,
        email_status=message.status if message else None,  # type: ignore[arg-type]
        email_error=message.last_error if message and message.status == "failed" else None,
        items=[
            OrderLine(
                id=item.id,
                position=item.position,
                product_id=item.product_id,
                product_sku=sku,
                product_unit=unit,
                description=item.description,
                quantity=quantity_text(item.quantity),
                unit_price=money_text(item.unit_price),
                vat_rate=item.vat_rate,
                discount_rate=quantity_text(item.discount_rate),
                line_discount=money_text(item.line_discount),
                line_subtotal=money_text(item.line_subtotal),
                line_vat=money_text(item.line_vat),
                line_total=money_text(item.line_total),
            )
            for item, sku, unit in lines
        ],
    )
