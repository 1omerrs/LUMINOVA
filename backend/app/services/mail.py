"""Outgoing e-mail through n8n.

LUMINOVA writes each message to `email_messages` in the same transaction as the
business change. The worker posts it, signed, to MAIL_WEBHOOK_URL; the n8n
workflow sends it over SMTP and reports the result either in its response or
later through POST /api/v1/mail/callback.
"""

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import escape

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.identity import Company
from app.models.mail import EmailMessage

RETRY_DELAYS = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=30), timedelta(hours=2), timedelta(hours=12))
MAX_ATTEMPTS = len(RETRY_DELAYS) + 1
LEASE = timedelta(minutes=2)
TIMEOUT = 30.0
TOLERANCE_SECONDS = 300
KEEP_BODY = timedelta(hours=24)
FINAL = ("sent", "failed")
USER_AGENT = "LUMINOVA-Mail/1"


def signature(secret: str, timestamp: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()

KIND_LABELS = {
    "verify_email": "E-posta doğrulama",
    "password_reset": "Şifre sıfırlama",
    "invitation": "Ekip daveti",
    "notification": "Bildirim",
    "digest": "Haftalık özet",
    "quote": "Müşteriye teklif",
}


class MailError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


def configured() -> bool:
    settings = get_settings()
    return bool(settings.mail_webhook_url and settings.mail_webhook_secret)


def absolute(path: str) -> str:
    return f"{get_settings().public_app_url}{path}"


@dataclass(frozen=True)
class Draft:
    subject: str
    text: str
    html: str


def _layout(
    title: str,
    paragraphs: list[str],
    action: tuple[str, str] | None = None,
    footer: str | None = None,
    *,
    highlight: tuple[int, str] | None = None,
) -> Draft:
    """`highlight` is (paragraph index, value): the value is shown large right after that paragraph."""
    text_lines = [title, ""]
    html_parts = [
        '<div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto;padding:24px;color:#1d1d1f">',
        '<p style="font-size:13px;letter-spacing:.12em;color:#6b6b73;margin:0 0 16px">LUMINOVA</p>',
        f'<h1 style="font-size:20px;margin:0 0 16px">{escape(title)}</h1>',
    ]
    for index, line in enumerate(paragraphs):
        text_lines.append(line)
        html_parts.append(f'<p style="font-size:15px;line-height:1.55;margin:0 0 12px">{escape(line)}</p>')
        if highlight and highlight[0] == index + 1:
            text_lines += ["", highlight[1], ""]
            html_parts.append(
                '<p style="margin:4px 0 18px;font-size:32px;font-weight:700;letter-spacing:.3em;font-family:Consolas,Menlo,monospace">'
                f"{escape(highlight[1])}</p>"
            )
    if action:
        label, url = action
        text_lines += ["", f"{label}: {url}"]
        html_parts.append(
            f'<p style="margin:20px 0"><a href="{escape(url, quote=True)}" style="background:#17171c;color:#ffffff;padding:12px 18px;'
            f'border-radius:8px;text-decoration:none;font-weight:600;display:inline-block">{escape(label)}</a></p>'
            f'<p style="font-size:12px;color:#6b6b73;word-break:break-all">Düğme çalışmazsa bu adresi tarayıcınıza yapıştırın: {escape(url)}</p>'
        )
    if footer:
        text_lines += ["", footer]
        html_parts.append(f'<p style="font-size:12px;color:#6b6b73;margin-top:24px">{escape(footer)}</p>')
    html_parts.append("</div>")
    return Draft(subject=title, text="\n".join(text_lines), html="".join(html_parts))


def simple_mail(title: str, paragraphs: list[str], action: tuple[str, str] | None = None) -> Draft:
    return _layout(title, paragraphs, action)


def verification_mail(first_name: str, code: str, raw_token: str, minutes: int) -> Draft:
    return _layout(
        f"Doğrulama kodunuz: {code}",
        [
            f"Merhaba {first_name},",
            "LUMINOVA kayıt ekranındaki kutuya bu kodu girin:",
            f"Kod {minutes} dakika geçerlidir; kimseyle paylaşmayın. İsterseniz aşağıdaki düğmeyle de doğrulayabilirsiniz.",
        ],
        ("E-postamı doğrula", absolute(f"/dogrula?token={raw_token}")),
        "Bu hesabı siz açmadıysanız bu iletiyi yok sayabilirsiniz.",
        highlight=(2, code),
    )


def reset_mail(first_name: str, raw_token: str) -> Draft:
    return _layout(
        "Şifre sıfırlama bağlantınız",
        [f"Merhaba {first_name},", "Şifrenizi sıfırlamak için aşağıdaki bağlantıyı kullanın. Bağlantı 1 saat geçerlidir ve bir kez kullanılabilir."],
        ("Yeni şifre belirle", absolute(f"/sifre-sifirla?token={raw_token}")),
        "Bu isteği siz yapmadıysanız şifreniz değişmez; iletiyi yok sayabilirsiniz.",
    )


def invitation_mail(company_name: str, inviter: str, role_label: str, raw_token: str, days: int) -> Draft:
    return _layout(
        f"{company_name} sizi LUMINOVA'ya davet etti",
        [f"{inviter}, sizi {company_name} çalışma alanına {role_label} olarak davet etti.", f"Davet {days} gün geçerlidir."],
        ("Daveti kabul et", absolute(f"/davet?token={raw_token}")),
        "Bu daveti beklemiyorsanız iletiyi yok sayabilirsiniz.",
    )


def notification_mail(company_name: str, title: str, body: str | None, link: str | None) -> Draft:
    draft = _layout(
        title,
        [line for line in (body, f"{company_name} çalışma alanından gelen bildirim.") if line],
        ("LUMINOVA'da aç", absolute(link)) if link else None,
        "Bu e-postaları Profil → Bildirim tercihleri bölümünden kapatabilirsiniz.",
    )
    return Draft(subject=f"{title} · {company_name}"[:200], text=draft.text, html=draft.html)


@dataclass(frozen=True)
class QuoteLine:
    description: str
    quantity: str
    total: str


def quote_mail(
    *,
    company_name: str,
    customer_name: str,
    code: str,
    lines: list[QuoteLine],
    total: str,
    valid_until: str | None,
    message: str | None,
    sender: str,
    url: str,
) -> Draft:
    title = f"{company_name} teklifi · {code}"
    intro = f"{company_name} olarak hazırladığımız {code} numaralı teklifi bilgilerinize sunarız."
    validity = f"Teklif {valid_until} tarihine kadar geçerlidir." if valid_until else None
    action = "Teklifi görüntülemek, kabul etmek veya reddetmek için aşağıdaki bağlantıyı kullanabilirsiniz."
    text = [title, "", f"Sayın {customer_name},", "", intro]
    if message:
        text += ["", message]
    text += ["", *[f"- {line.description} · {line.quantity} · {line.total}" for line in lines], f"Genel toplam: {total}"]
    if validity:
        text.append(validity)
    text += ["", action, f"Teklifi aç: {url}", "", "Saygılarımızla,", sender, company_name]

    rows = "".join(
        f'<tr><td style="padding:8px 0;border-bottom:1px solid #ececf0;font-size:14px">{escape(line.description)}</td>'
        f'<td style="padding:8px 8px;border-bottom:1px solid #ececf0;font-size:14px;text-align:right;white-space:nowrap">{escape(line.quantity)}</td>'
        f'<td style="padding:8px 0;border-bottom:1px solid #ececf0;font-size:14px;text-align:right;white-space:nowrap">{escape(line.total)}</td></tr>'
        for line in lines
    )
    paragraphs = [f"Sayın {customer_name},", intro, *([message] if message else [])]
    html = [
        '<div style="font-family:Arial,Helvetica,sans-serif;max-width:600px;margin:0 auto;padding:24px;color:#1d1d1f">',
        f'<p style="font-size:13px;letter-spacing:.08em;color:#6b6b73;margin:0 0 16px">{escape(company_name.upper())}</p>',
        f'<h1 style="font-size:20px;margin:0 0 16px">{escape(code)} numaralı teklif</h1>',
        *[f'<p style="font-size:15px;line-height:1.55;margin:0 0 12px;white-space:pre-line">{escape(line)}</p>' for line in paragraphs],
        f'<table style="width:100%;border-collapse:collapse;margin:16px 0">{rows}'
        f'<tr><td colspan="2" style="padding:10px 0;font-size:15px;font-weight:bold">Genel toplam</td>'
        f'<td style="padding:10px 0;font-size:15px;font-weight:bold;text-align:right;white-space:nowrap">{escape(total)}</td></tr></table>',
    ]
    if validity:
        html.append(f'<p style="font-size:14px;color:#3a3a42;margin:0 0 12px">{escape(validity)}</p>')
    html += [
        f'<p style="font-size:14px;margin:0 0 4px">{escape(action)}</p>',
        f'<p style="margin:16px 0"><a href="{escape(url, quote=True)}" style="background:#17171c;color:#ffffff;padding:12px 18px;'
        'border-radius:8px;text-decoration:none;font-weight:600;display:inline-block">Teklifi görüntüle</a></p>',
        f'<p style="font-size:12px;color:#6b6b73;word-break:break-all">Düğme çalışmazsa bu adresi tarayıcınıza yapıştırın: {escape(url)}</p>',
        f'<p style="font-size:14px;margin-top:24px">Saygılarımızla,<br>{escape(sender)}<br>{escape(company_name)}</p>',
        "</div>",
    ]
    return Draft(subject=title[:200], text="\n".join(text), html="".join(html))


def digest_mail(company_name: str, first_name: str, period: str, sections: list[tuple[str, list[str], str]]) -> Draft:
    title = f"Haftalık özet · {company_name}"
    text = [title, period, "", f"Merhaba {first_name}, bu hafta öne çıkanlar:"]
    html = [
        '<div style="font-family:Arial,Helvetica,sans-serif;max-width:600px;margin:0 auto;padding:24px;color:#1d1d1f">',
        '<p style="font-size:13px;letter-spacing:.12em;color:#6b6b73;margin:0 0 16px">LUMINOVA</p>',
        f'<h1 style="font-size:20px;margin:0 0 4px">{escape(title)}</h1>',
        f'<p style="font-size:13px;color:#6b6b73;margin:0 0 16px">{escape(period)}</p>',
        f'<p style="font-size:15px;margin:0 0 16px">Merhaba {escape(first_name)}, bu hafta öne çıkanlar:</p>',
    ]
    for heading, lines, link in sections:
        url = absolute(link)
        text += ["", heading.replace("i", "İ").replace("ı", "I").upper(), *[f"- {line}" for line in lines], f"Aç: {url}"]
        html.append(f'<h2 style="font-size:15px;margin:20px 0 6px">{escape(heading)}</h2><ul style="margin:0;padding-left:18px">')
        html += [f'<li style="font-size:14px;line-height:1.55;margin:0 0 4px">{escape(line)}</li>' for line in lines]
        html.append(f'</ul><p style="margin:6px 0 0"><a href="{escape(url, quote=True)}" style="color:#5b47d6;font-size:13px">LUMINOVA\'da aç</a></p>')
    footer = "Bu özeti Profil → Bildirimler bölümündeki “Haftalık özet” anahtarıyla kapatabilirsiniz."
    text += ["", footer]
    html.append(f'<p style="font-size:12px;color:#6b6b73;margin-top:24px">{escape(footer)}</p></div>')
    return Draft(subject=f"{title} · {period}"[:200], text="\n".join(text), html="".join(html))


def enqueue(
    db: Session,
    *,
    kind: str,
    to: str,
    draft: Draft,
    company_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    ref: str | None = None,
    reply_to: str | None = None,
) -> EmailMessage | None:
    """Adds the message to the session without committing. Returns None when no mail webhook is configured."""
    if not configured():
        return None
    now = datetime.now(UTC)
    message = EmailMessage(
        id=uuid.uuid4(),
        company_id=company_id,
        user_id=user_id,
        kind=kind,
        ref=ref,
        to_email=to,
        reply_to=reply_to,
        subject=draft.subject[:200],
        body_text=draft.text,
        body_html=draft.html,
        status="queued",
        next_attempt_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(message)
    return message


def _finish(message: EmailMessage, status: str, *, error: str | None = None, provider_id: str | None = None) -> None:
    now = datetime.now(UTC)
    message.status = status
    message.updated_at = now
    message.next_attempt_at = None
    if error is not None:
        message.last_error = error[:400]
    if provider_id:
        message.provider_message_id = provider_id[:200]
    if status == "sent":
        message.sent_at = now
        message.last_error = None
        message.body_text = None
        message.body_html = None


def _outcome(payload: object) -> tuple[str, str | None, str | None]:
    """Reads the n8n response. The SMTP node returns accepted/rejected/messageId; a custom response may send status."""
    if isinstance(payload, list) and payload:
        payload = payload[0]
    if not isinstance(payload, dict):
        return "handed_off", None, None
    if isinstance(payload.get("json"), dict):
        payload = payload["json"]
    provider_id = payload.get("messageId") or payload.get("message_id")
    provider_id = str(provider_id) if provider_id else None
    status = payload.get("status")
    accepted = payload.get("accepted")
    rejected = payload.get("rejected")
    if status == "failed":
        return "failed", str(payload.get("error") or "n8n gönderimin başarısız olduğunu bildirdi.")[:400], provider_id
    if isinstance(rejected, list) and rejected and not accepted:
        return "failed", "SMTP sunucusu alıcıyı reddetti.", provider_id
    if status == "sent" or (isinstance(accepted, list) and accepted) or provider_id:
        return "sent", None, provider_id
    return "handed_off", None, provider_id


def _post(message: EmailMessage, client: httpx.Client | None) -> tuple[int | None, object, str | None]:
    settings = get_settings()
    envelope = {
        "id": str(message.id),
        "kind": message.kind,
        "to": message.to_email,
        "reply_to": message.reply_to,
        "subject": message.subject,
        "text": message.body_text,
        "html": message.body_html,
        "created_at": message.created_at.isoformat(),
    }
    body = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "X-Luminova-Event": "mail.send",
        "X-Luminova-Delivery": str(message.id),
        "X-Luminova-Timestamp": timestamp,
        "X-Luminova-Signature": signature(settings.mail_webhook_secret, timestamp, body),
    }
    try:
        if client is not None:
            response = client.post(settings.mail_webhook_url, content=body, headers=headers)
        else:
            with httpx.Client(timeout=TIMEOUT, follow_redirects=False) as own:
                response = own.post(settings.mail_webhook_url, content=body, headers=headers)
    except httpx.HTTPError as error:
        return None, None, f"n8n'e bağlanılamadı: {type(error).__name__}"
    if not 200 <= response.status_code < 300:
        return response.status_code, None, f"n8n {response.status_code} yanıtı verdi."
    try:
        payload = response.json()
    except ValueError:
        payload = None
    return response.status_code, payload, None


def attempt(db: Session, message: EmailMessage, client: httpx.Client | None = None) -> EmailMessage:
    if not configured():
        message.next_attempt_at = datetime.now(UTC) + RETRY_DELAYS[0]
        message.last_error = "E-posta webhook adresi tanımlı değil."
        db.commit()
        return message
    if message.body_text is None:
        _finish(message, "failed", error="İleti içeriği silinmiş; gönderilemez.")
        db.commit()
        return message
    _code, payload, error = _post(message, client)
    message.attempts += 1
    message.updated_at = datetime.now(UTC)
    if error is not None:
        message.last_error = error
        if message.attempts >= MAX_ATTEMPTS:
            _finish(message, "failed")
        else:
            message.next_attempt_at = message.updated_at + RETRY_DELAYS[message.attempts - 1]
        db.commit()
        return message
    status, failure, provider_id = _outcome(payload)
    message.handed_off_at = message.updated_at
    if status == "handed_off":
        message.status = "handed_off"
        message.next_attempt_at = None
        message.last_error = None
        if provider_id:
            message.provider_message_id = provider_id[:200]
    else:
        _finish(message, status, error=failure, provider_id=provider_id)
    db.commit()
    return message


def deliver_mail(db: Session, limit: int = 20, client: httpx.Client | None = None) -> int:
    now = datetime.now(UTC)
    db.execute(
        update(EmailMessage)
        .where(
            EmailMessage.body_text.is_not(None),
            or_(EmailMessage.status.in_(("handed_off", "failed")), EmailMessage.created_at < now - timedelta(days=8)),
            EmailMessage.updated_at < now - KEEP_BODY,
        )
        .values(body_text=None, body_html=None)
    )
    db.commit()
    if not configured():
        return 0
    rows = db.scalars(
        select(EmailMessage)
        .where(EmailMessage.status == "queued", EmailMessage.next_attempt_at <= now)
        .order_by(EmailMessage.next_attempt_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    for row in rows:
        row.next_attempt_at = now + LEASE
    db.commit()
    for row in rows:
        attempt(db, row, client)
    return len(rows)


class CallbackInput(BaseModel):
    id: uuid.UUID
    status: str = Field(pattern="^(sent|failed)$")
    error: str | None = Field(default=None, max_length=400)
    message_id: str | None = Field(default=None, max_length=200)


def handle_callback(db: Session, headers: dict[str, str], body: bytes) -> EmailMessage:
    if not configured():
        raise MailError(404, "E-posta kanalı yapılandırılmamış.")
    timestamp = headers.get("x-luminova-timestamp", "")
    given = headers.get("x-luminova-signature", "")
    if not timestamp.isdigit() or abs(time.time() - int(timestamp)) > TOLERANCE_SECONDS:
        raise MailError(401, "İstek zaman damgası geçersiz veya süresi dolmuş.")
    if not hmac.compare_digest(given, signature(get_settings().mail_webhook_secret, timestamp, body)):
        raise MailError(401, "İmza doğrulanamadı.")
    try:
        data = CallbackInput.model_validate_json(body)
    except ValidationError:
        raise MailError(422, "Gövde okunamadı. id ve status (sent veya failed) gönderin.") from None
    message = db.scalar(select(EmailMessage).where(EmailMessage.id == data.id).with_for_update())
    if message is None:
        raise MailError(404, "E-posta kaydı bulunamadı.")
    if message.status not in FINAL:
        failure = (data.error or "n8n gönderimin başarısız olduğunu bildirdi.") if data.status == "failed" else None
        _finish(message, data.status, error=failure, provider_id=data.message_id)
        db.commit()
    return message


def latest_status(db: Session, refs: list[str]) -> dict[str, EmailMessage]:
    if not refs:
        return {}
    found: dict[str, EmailMessage] = {}
    for row in db.scalars(select(EmailMessage).where(EmailMessage.ref.in_(refs)).order_by(EmailMessage.created_at)):
        if row.ref:
            found[row.ref] = row
    return found


def list_messages(db: Session, status: str | None, limit: int = 50) -> tuple[list[tuple[EmailMessage, str | None]], dict[str, int]]:
    statement = select(EmailMessage, Company.name).outerjoin(Company, Company.id == EmailMessage.company_id)
    if status:
        statement = statement.where(EmailMessage.status == status)
    rows = db.execute(statement.order_by(EmailMessage.created_at.desc()).limit(limit)).all()
    counts = dict(db.execute(select(EmailMessage.status, func.count()).group_by(EmailMessage.status)).all())
    return [(row[0], row[1]) for row in rows], {key: int(value) for key, value in counts.items()}


def retry(db: Session, message_id: uuid.UUID) -> EmailMessage:
    message = db.scalar(select(EmailMessage).where(EmailMessage.id == message_id).with_for_update())
    if message is None:
        raise MailError(404, "E-posta kaydı bulunamadı.")
    if message.status != "failed":
        raise MailError(409, "Yalnızca başarısız e-postalar yeniden denenebilir.")
    if message.body_text is None:
        raise MailError(409, "Bu iletinin içeriği güvenlik için silindi. İşlemi yeniden başlatın (ör. daveti yeniden gönderin).")
    message.status = "queued"
    message.attempts = 0
    message.next_attempt_at = datetime.now(UTC)
    message.updated_at = message.next_attempt_at
    db.commit()
    return message
