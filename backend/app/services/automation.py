"""Outgoing signed webhooks (event outbox) and signed incoming webhooks.

Secrets are derived from WEBHOOK_SECRET_KEY, the endpoint id and a version
number, so no secret value is stored in the database.
"""

import base64
import hashlib
import hmac
import ipaddress
import json
import socket
import time
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.automation import AutomationEvent, WebhookDelivery, WebhookEndpoint
from app.models.identity import AuditLog, Company, CompanyMembership, User
from app.modules.tasks.models import Task
from app.schemas.automation import (
    DeliveryItem,
    EndpointCreated,
    EndpointInput,
    EndpointItem,
    EventType,
    InboundNotification,
    InboundRequest,
    InboundResult,
    InboundTask,
)
from app.services.auth import Member
from app.services.modules import enabled_keys
from app.services.notifications import notify

EVENT_TYPES: dict[str, tuple[str, str]] = {
    "customer.created": ("Müşteri eklendi", "Yeni müşteri kaydı açıldığında."),
    "order.created": ("Sipariş oluşturuldu", "Yeni satış siparişi kaydedildiğinde."),
    "order.status_changed": ("Sipariş durumu değişti", "Sipariş onaylandığında, teslim edildiğinde veya iptal edildiğinde."),
    "quote.status_changed": ("Teklif durumu değişti", "Teklif gönderildi, kabul edildi veya reddedildi olarak işaretlendiğinde."),
    "stock.low": ("Stok kritik seviyede", "Bir ürün minimum stok seviyesinin altına düştüğünde."),
    "task.completed": ("Görev tamamlandı", "Bir görev tamamlandı durumuna geçtiğinde."),
    "finance.record_created": ("Finans kaydı eklendi", "Gelir veya gider kaydı oluşturulduğunda."),
    "production.completed": ("Üretim tamamlandı", "Bir iş emri tamamlandığında."),
}
RETRY_DELAYS = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=30), timedelta(hours=2), timedelta(hours=12))
MAX_ATTEMPTS = len(RETRY_DELAYS) + 1
LEASE = timedelta(minutes=2)
TIMEOUT = 10.0
TOLERANCE_SECONDS = 300
ENDPOINT_LIMIT = 10
USER_AGENT = "LUMINOVA-Webhooks/1"


class AutomationError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


def event_types() -> list[EventType]:
    return [EventType(key=key, label=label, description=description) for key, (label, description) in EVENT_TYPES.items()]


def endpoint_secret(endpoint: WebhookEndpoint) -> str:
    key = get_settings().webhook_secret_key.encode()
    digest = hmac.new(key, f"webhook:{endpoint.id}:{endpoint.secret_version}".encode(), hashlib.sha256).digest()
    return "whsec_" + base64.urlsafe_b64encode(digest).decode().rstrip("=")


def signature(secret: str, timestamp: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def _manager(member: Member) -> None:
    if member.role not in {"owner", "admin"}:
        raise AutomationError(403, "Otomasyon bağlantılarını çalışma alanı sahibi veya yöneticisi yönetebilir.")


def _check_url(url: str | None) -> str:
    if not url:
        raise AutomationError(422, "Webhook adresini girin.")
    parts = urlsplit(url)
    production = get_settings().app_env == "production"
    allowed = {"https"} if production else {"https", "http"}
    if parts.scheme not in allowed or not parts.hostname:
        raise AutomationError(422, "Adres https:// ile başlamalı." if production else "Adres http:// veya https:// ile başlamalı.")
    if parts.username or parts.password:
        raise AutomationError(422, "Adreste kullanıcı adı veya şifre olmamalı.")
    if production:
        try:
            addresses = {info[4][0] for info in socket.getaddrinfo(parts.hostname, parts.port or 443)}
        except socket.gaierror:
            raise AutomationError(422, "Adresin alan adı çözümlenemedi.") from None
        for address in addresses:
            ip = ipaddress.ip_address(address.split("%")[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise AutomationError(422, "İç ağ adreslerine webhook gönderilemez.")
    return url


def _check_events(events: list[str]) -> list[str]:
    unknown = [event for event in events if event not in EVENT_TYPES]
    if unknown:
        raise AutomationError(422, f"Bilinmeyen olay türü: {unknown[0]}")
    if not events:
        raise AutomationError(422, "En az bir olay seçin.")
    return sorted(set(events), key=list(EVENT_TYPES).index)


def _item(db: Session, endpoint: WebhookEndpoint) -> EndpointItem:
    counts = dict(
        db.execute(
            select(WebhookDelivery.status, func.count())
            .where(WebhookDelivery.endpoint_id == endpoint.id, WebhookDelivery.status != "delivered")
            .group_by(WebhookDelivery.status)
        ).all()
    )
    return EndpointItem(
        id=endpoint.id,
        direction=endpoint.direction,  # type: ignore[arg-type]
        name=endpoint.name,
        url=endpoint.url,
        inbound_path=f"/api/v1/hooks/{endpoint.id}" if endpoint.direction == "inbound" else None,
        events=list(endpoint.events or []),
        active=endpoint.active,
        secret_hint=endpoint.secret_hint,
        last_used_at=endpoint.last_used_at,
        created_at=endpoint.created_at,
        pending=int(counts.get("pending", 0)),
        failed=int(counts.get("failed", 0)),
    )


def _owned(db: Session, member: Member, endpoint_id: uuid.UUID, *, lock: bool = False) -> WebhookEndpoint:
    statement = select(WebhookEndpoint).where(
        WebhookEndpoint.id == endpoint_id, WebhookEndpoint.company_id == member.company.id, WebhookEndpoint.deleted_at.is_(None)
    )
    endpoint = db.scalar(statement.with_for_update() if lock else statement)
    if endpoint is None:
        raise AutomationError(404, "Bağlantı bulunamadı.")
    return endpoint


def _audit(member: Member, action: str, endpoint: WebhookEndpoint) -> AuditLog:
    return AuditLog(
        company_id=member.company.id,
        actor_user_id=member.user.id,
        action=action,
        entity_type="webhook_endpoint",
        entity_id=str(endpoint.id),
        summary={"name": endpoint.name, "direction": endpoint.direction},
        source="api",
    )


def list_endpoints(db: Session, member: Member) -> list[EndpointItem]:
    _manager(member)
    rows = db.scalars(
        select(WebhookEndpoint)
        .where(WebhookEndpoint.company_id == member.company.id, WebhookEndpoint.deleted_at.is_(None))
        .order_by(WebhookEndpoint.created_at)
    ).all()
    return [_item(db, row) for row in rows]


def create_endpoint(db: Session, member: Member, data: EndpointInput) -> EndpointCreated:
    _manager(member)
    count = db.scalar(
        select(func.count()).select_from(WebhookEndpoint).where(WebhookEndpoint.company_id == member.company.id, WebhookEndpoint.deleted_at.is_(None))
    )
    if int(count or 0) >= ENDPOINT_LIMIT:
        raise AutomationError(409, f"Bir çalışma alanında en çok {ENDPOINT_LIMIT} bağlantı olabilir.")
    outbound = data.direction == "outbound"
    endpoint = WebhookEndpoint(
        id=uuid.uuid4(),
        company_id=member.company.id,
        direction=data.direction,
        name=data.name,
        url=_check_url(data.url) if outbound else None,
        events=_check_events(data.events) if outbound else [],
        active=data.active,
        secret_version=1,
        secret_hint="",
        created_by=member.user.id,
    )
    secret = endpoint_secret(endpoint)
    endpoint.secret_hint = secret[-4:]
    db.add(endpoint)
    db.add(_audit(member, "automation.endpoint_created", endpoint))
    db.commit()
    db.refresh(endpoint)
    return EndpointCreated(endpoint=_item(db, endpoint), secret=secret)


def update_endpoint(db: Session, member: Member, endpoint_id: uuid.UUID, data: EndpointInput) -> EndpointItem:
    _manager(member)
    endpoint = _owned(db, member, endpoint_id, lock=True)
    endpoint.name = data.name
    endpoint.active = data.active
    if endpoint.direction == "outbound":
        endpoint.url = _check_url(data.url)
        endpoint.events = _check_events(data.events)
    endpoint.updated_at = datetime.now(UTC)
    db.add(_audit(member, "automation.endpoint_updated", endpoint))
    db.commit()
    return _item(db, endpoint)


def rotate_secret(db: Session, member: Member, endpoint_id: uuid.UUID) -> EndpointCreated:
    _manager(member)
    endpoint = _owned(db, member, endpoint_id, lock=True)
    endpoint.secret_version += 1
    secret = endpoint_secret(endpoint)
    endpoint.secret_hint = secret[-4:]
    endpoint.updated_at = datetime.now(UTC)
    db.add(_audit(member, "automation.secret_rotated", endpoint))
    db.commit()
    return EndpointCreated(endpoint=_item(db, endpoint), secret=secret)


def delete_endpoint(db: Session, member: Member, endpoint_id: uuid.UUID) -> None:
    _manager(member)
    endpoint = _owned(db, member, endpoint_id, lock=True)
    now = datetime.now(UTC)
    endpoint.deleted_at = now
    endpoint.active = False
    db.execute(
        update(WebhookDelivery)
        .where(WebhookDelivery.endpoint_id == endpoint.id, WebhookDelivery.status == "pending")
        .values(status="failed", last_error="Bağlantı silindi.", next_attempt_at=None, updated_at=now)
    )
    db.add(_audit(member, "automation.endpoint_deleted", endpoint))
    db.commit()


def _envelope(event: AutomationEvent, company: Company) -> dict[str, object]:
    return {
        "id": str(event.id),
        "type": event.event_type,
        "occurred_at": event.created_at.isoformat(),
        "company": {"id": str(company.id), "slug": company.slug},
        "data": event.payload,
    }


def emit(db: Session, member: Member, event_type: str, data: dict[str, object]) -> None:
    if event_type not in EVENT_TYPES or "automation" not in enabled_keys(db, member):
        return
    endpoints = db.scalars(
        select(WebhookEndpoint.id).where(
            WebhookEndpoint.company_id == member.company.id,
            WebhookEndpoint.direction == "outbound",
            WebhookEndpoint.active.is_(True),
            WebhookEndpoint.deleted_at.is_(None),
            WebhookEndpoint.events.contains([event_type]),
        )
    ).all()
    if not endpoints:
        return
    now = datetime.now(UTC)
    event = AutomationEvent(id=uuid.uuid4(), company_id=member.company.id, direction="outbound", event_type=event_type, payload=data, created_at=now)
    db.add(event)
    db.flush()
    for endpoint_id in endpoints:
        db.add(WebhookDelivery(company_id=member.company.id, endpoint_id=endpoint_id, event_id=event.id, status="pending", next_attempt_at=now))


def _send(endpoint: WebhookEndpoint, delivery: WebhookDelivery, envelope: dict[str, object], client: httpx.Client | None) -> tuple[int | None, str | None]:
    body = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "X-Luminova-Event": str(envelope["type"]),
        "X-Luminova-Delivery": str(delivery.id),
        "X-Luminova-Timestamp": timestamp,
        "X-Luminova-Signature": signature(endpoint_secret(endpoint), timestamp, body),
    }
    try:
        if client is not None:
            response = client.post(endpoint.url or "", content=body, headers=headers)
        else:
            with httpx.Client(timeout=TIMEOUT, follow_redirects=False) as own:
                response = own.post(endpoint.url or "", content=body, headers=headers)
    except httpx.HTTPError as error:
        return None, f"Bağlantı kurulamadı: {type(error).__name__}"
    if 200 <= response.status_code < 300:
        return response.status_code, None
    return response.status_code, f"Alıcı {response.status_code} yanıtı verdi."


def attempt(db: Session, delivery: WebhookDelivery, client: httpx.Client | None = None) -> WebhookDelivery:
    endpoint = db.get(WebhookEndpoint, delivery.endpoint_id)
    event = db.get(AutomationEvent, delivery.event_id)
    company = db.get(Company, delivery.company_id)
    now = datetime.now(UTC)
    if endpoint is None or event is None or company is None or endpoint.deleted_at is not None or not endpoint.active:
        delivery.status, delivery.next_attempt_at, delivery.last_error = "failed", None, "Bağlantı kapalı."
        delivery.updated_at = now
        db.commit()
        return delivery
    if get_settings().app_env == "production":
        try:
            _check_url(endpoint.url)
        except AutomationError as error:
            delivery.status, delivery.next_attempt_at, delivery.last_error = "failed", None, error.detail
            delivery.updated_at = now
            db.commit()
            return delivery
    code, error = _send(endpoint, delivery, _envelope(event, company), client)
    delivery.attempts += 1
    delivery.last_status_code = code
    delivery.last_error = error
    delivery.updated_at = datetime.now(UTC)
    if error is None:
        delivery.status, delivery.delivered_at, delivery.next_attempt_at = "delivered", delivery.updated_at, None
        endpoint.last_used_at = delivery.updated_at
    elif delivery.attempts >= MAX_ATTEMPTS:
        delivery.status, delivery.next_attempt_at = "failed", None
    else:
        delivery.next_attempt_at = delivery.updated_at + RETRY_DELAYS[delivery.attempts - 1]
    db.commit()
    return delivery


def deliver_due(db: Session, limit: int = 20, client: httpx.Client | None = None) -> int:
    now = datetime.now(UTC)
    rows = db.scalars(
        select(WebhookDelivery)
        .where(WebhookDelivery.status == "pending", WebhookDelivery.next_attempt_at <= now)
        .order_by(WebhookDelivery.next_attempt_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    for row in rows:
        row.next_attempt_at = now + LEASE
    db.commit()
    for row in rows:
        attempt(db, row, client)
    return len(rows)


def _delivery_items(db: Session, rows: list[WebhookDelivery]) -> list[DeliveryItem]:
    if not rows:
        return []
    names = {endpoint.id: endpoint.name for endpoint in db.scalars(select(WebhookEndpoint).where(WebhookEndpoint.id.in_({row.endpoint_id for row in rows})))}
    types = dict(db.execute(select(AutomationEvent.id, AutomationEvent.event_type).where(AutomationEvent.id.in_({row.event_id for row in rows}))).all())
    return [
        DeliveryItem(
            id=row.id,
            endpoint_id=row.endpoint_id,
            endpoint_name=names.get(row.endpoint_id, "Silinmiş bağlantı"),
            event_type=types.get(row.event_id, ""),
            status=row.status,  # type: ignore[arg-type]
            attempts=row.attempts,
            last_status_code=row.last_status_code,
            last_error=row.last_error,
            next_attempt_at=row.next_attempt_at,
            delivered_at=row.delivered_at,
            created_at=row.created_at,
        )
        for row in rows
    ]


def list_deliveries(db: Session, member: Member, endpoint_id: uuid.UUID | None) -> list[DeliveryItem]:
    _manager(member)
    conditions = [WebhookDelivery.company_id == member.company.id]
    if endpoint_id is not None:
        conditions.append(WebhookDelivery.endpoint_id == endpoint_id)
    rows = db.scalars(select(WebhookDelivery).where(*conditions).order_by(WebhookDelivery.created_at.desc()).limit(50)).all()
    return _delivery_items(db, list(rows))


def send_test(db: Session, member: Member, endpoint_id: uuid.UUID, client: httpx.Client | None = None) -> DeliveryItem:
    _manager(member)
    endpoint = _owned(db, member, endpoint_id)
    if endpoint.direction != "outbound":
        raise AutomationError(409, "Deneme gönderimi yalnızca giden bağlantılar içindir.")
    now = datetime.now(UTC)
    event = AutomationEvent(
        id=uuid.uuid4(),
        company_id=member.company.id,
        direction="outbound",
        event_type="ping",
        payload={"message": "LUMINOVA deneme olayı", "requested_by": f"{member.user.first_name} {member.user.last_name}"},
        created_at=now,
    )
    db.add(event)
    db.flush()
    delivery = WebhookDelivery(company_id=member.company.id, endpoint_id=endpoint.id, event_id=event.id, status="pending", next_attempt_at=now + LEASE)
    db.add(delivery)
    db.commit()
    delivery = attempt(db, delivery, client)
    if delivery.status == "pending":
        delivery.status, delivery.next_attempt_at = "failed", None
        db.commit()
    return _delivery_items(db, [delivery])[0]


def retry_delivery(db: Session, member: Member, delivery_id: uuid.UUID, client: httpx.Client | None = None) -> DeliveryItem:
    _manager(member)
    delivery = db.scalar(select(WebhookDelivery).where(WebhookDelivery.id == delivery_id, WebhookDelivery.company_id == member.company.id).with_for_update())
    if delivery is None:
        raise AutomationError(404, "Gönderim bulunamadı.")
    if delivery.status == "delivered":
        raise AutomationError(409, "Bu gönderim zaten iletildi.")
    delivery.status = "pending"
    delivery.attempts = min(delivery.attempts, MAX_ATTEMPTS - 1)
    delivery.next_attempt_at = datetime.now(UTC) + LEASE
    db.commit()
    return _delivery_items(db, [attempt(db, delivery, client)])[0]


def handle_inbound(db: Session, endpoint_id: uuid.UUID, headers: dict[str, str], body: bytes) -> InboundResult:
    endpoint = db.scalar(
        select(WebhookEndpoint).where(WebhookEndpoint.id == endpoint_id, WebhookEndpoint.direction == "inbound", WebhookEndpoint.deleted_at.is_(None))
    )
    if endpoint is None or not endpoint.active:
        raise AutomationError(404, "Bağlantı bulunamadı.")
    timestamp = headers.get("x-luminova-timestamp", "")
    given = headers.get("x-luminova-signature", "")
    if not timestamp.isdigit() or abs(time.time() - int(timestamp)) > TOLERANCE_SECONDS:
        raise AutomationError(401, "İstek zaman damgası geçersiz veya süresi dolmuş.")
    if not hmac.compare_digest(given, signature(endpoint_secret(endpoint), timestamp, body)):
        raise AutomationError(401, "İmza doğrulanamadı.")
    try:
        request = InboundRequest.model_validate_json(body)
    except ValidationError:
        raise AutomationError(422, "İstek gövdesi okunamadı. action ve data alanlarını gönderin.") from None

    company = db.get(Company, endpoint.company_id)
    owner = db.get(User, company.owner_user_id) if company else None
    if company is None or owner is None or company.status != "active":
        raise AutomationError(404, "Bağlantı bulunamadı.")
    member = Member(user=owner, company=company, role="owner")
    enabled = enabled_keys(db, member)
    if "automation" not in enabled:
        raise AutomationError(403, "Otomasyonlar modülü bu çalışma alanında kapalı.")

    external_id = headers.get("x-luminova-delivery") or None
    if external_id is not None:
        external_id = external_id[:120]
        seen = db.scalar(select(AutomationEvent.id).where(AutomationEvent.endpoint_id == endpoint.id, AutomationEvent.external_id == external_id))
        if seen is not None:
            return InboundResult(ok=True, action=request.action, duplicate=True)

    now = datetime.now(UTC)
    created: uuid.UUID | None = None
    try:
        if request.action == "task.create":
            if "tasks" not in enabled:
                raise AutomationError(403, "Görev ve İş Yönetimi modülü kapalı.")
            data = InboundTask.model_validate(request.data)
            task = Task(
                id=uuid.uuid4(),
                company_id=company.id,
                title=" ".join(data.title.split()),
                description=data.description,
                priority=data.priority,
                due_date=data.due_date,
                status="todo",
            )
            db.add(task)
            created = task.id
            db.add(
                AuditLog(
                    company_id=company.id,
                    action="task.created",
                    entity_type="task",
                    entity_id=str(task.id),
                    summary={"fields": sorted(data.model_dump(exclude_none=True)), "via": endpoint.name},
                    source="webhook",
                )
            )
        else:
            note = InboundNotification.model_validate(request.data)
            managers = db.scalars(
                select(CompanyMembership.user_id).where(
                    CompanyMembership.company_id == company.id, CompanyMembership.status == "active", CompanyMembership.role.in_(("owner", "admin"))
                )
            ).all()
            for user_id in managers:
                notify(db, member, category="automation", title=note.title, body=note.body, user_id=user_id)
    except ValidationError as error:
        first = error.errors()[0]
        raise AutomationError(422, f"data.{'.'.join(str(part) for part in first['loc'])}: {first['msg']}") from None

    db.add(
        AutomationEvent(
            company_id=company.id,
            direction="inbound",
            event_type=request.action,
            payload={"data": request.data},
            endpoint_id=endpoint.id,
            external_id=external_id,
            created_at=now,
        )
    )
    endpoint.last_used_at = now
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return InboundResult(ok=True, action=request.action, duplicate=True)
    return InboundResult(ok=True, action=request.action, id=created)
