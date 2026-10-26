import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.identity import Company, CompanyMembership, User
from app.models.mail import EmailMessage
from app.models.notifications import Notification, NotificationPreference
from app.schemas.notifications import NotificationItem, NotificationListResponse, PreferenceItem
from app.services import mail
from app.services.auth import Member

LIST_LIMIT = 20
CATEGORIES: dict[str, tuple[str, str]] = {
    "tasks": ("Görevler", "Size atanan görevler, yarın teslim edilecek ve geciken görev hatırlatmaları."),
    "finance": ("Finans", "Vadesi yaklaşan ve geçen alacak ile borç hatırlatmaları."),
    "quotes": ("Teklifler", "Müşteri e-postayla gönderdiğiniz bir teklifi kabul ettiğinde veya reddettiğinde."),
    "inventory": ("Stok", "Bir ürün minimum stok seviyesinin altına düştüğünde veya kritik seviyeye indiğinde."),
    "team": ("Ekip", "Birisi katılım koduyla ekibe katılmak istediğinde, davet ettiğiniz biri katıldığında veya yetkileriniz değiştiğinde."),
    "support": ("Destek", "Destek talebinize LUMINOVA ekibinden yanıt geldiğinde."),
    "automation": ("Otomasyon", "n8n veya başka bir sistem gelen webhook ile bildirim gönderdiğinde."),
    "workspace": ("Çalışma alanı", "Modül tercihleri ve kurulum değişiklikleri."),
    "digest": (
        "Haftalık özet",
        "Her pazartesi 09:00'da görevleriniz; sahip ve yöneticiler için ayrıca satış, tahsilat, vade, stok ve proje durumu tek e-postada gelir.",
    ),
}
EMAIL_ONLY = {"digest"}
MANAGERS = ("owner", "admin")


def default_email(category: str, role: str | None) -> bool:
    """E-mail is opt-in except the weekly digest (everyone) and stock, quote and team news (owners and admins)."""
    if category == "digest":
        return True
    return category in {"inventory", "quotes", "team"} and role in MANAGERS


def preferences(db: Session, member: Member) -> list[PreferenceItem]:
    rows = {
        row.category: row
        for row in db.scalars(
            select(NotificationPreference).where(NotificationPreference.user_id == member.user.id, NotificationPreference.company_id == member.company.id)
        )
    }
    available = mail.configured()
    return [
        PreferenceItem(
            category=key,
            label=label,
            description=description,
            in_app=rows[key].in_app if key in rows else key not in EMAIL_ONLY,
            in_app_available=key not in EMAIL_ONLY,
            email=rows[key].email if key in rows else default_email(key, member.role),
            email_available=available,
        )
        for key, (label, description) in CATEGORIES.items()
    ]


def wants_email(db: Session, company_id: uuid.UUID, user_id: uuid.UUID, category: str) -> bool:
    preference = _preference(db, company_id, user_id, category)
    if preference is not None:
        return preference.email
    role = db.scalar(
        select(CompanyMembership.role).where(
            CompanyMembership.company_id == company_id, CompanyMembership.user_id == user_id, CompanyMembership.status == "active"
        )
    )
    return default_email(category, role)


def update_preferences(db: Session, member: Member, in_app: dict[str, bool], email: dict[str, bool] | None = None) -> list[PreferenceItem]:
    email = email or {}
    unknown = (set(in_app) | set(email)) - set(CATEGORIES)
    if unknown:
        raise NotificationError(422, "Bilinmeyen bildirim kategorisi.")
    if any(email.values()) and not mail.configured():
        raise NotificationError(409, "E-posta servisi yapılandırılmadığı için e-posta bildirimi açılamaz.")
    now = datetime.now(UTC)
    for category in set(in_app) | set(email):
        row = db.scalar(
            select(NotificationPreference).where(
                NotificationPreference.user_id == member.user.id,
                NotificationPreference.company_id == member.company.id,
                NotificationPreference.category == category,
            )
        )
        if row is None:
            row = NotificationPreference(
                company_id=member.company.id,
                user_id=member.user.id,
                category=category,
                in_app=category not in EMAIL_ONLY,
                email=default_email(category, member.role),
            )
            db.add(row)
        if category in in_app and category not in EMAIL_ONLY:
            row.in_app = in_app[category]
        if category in email:
            row.email = email[category]
        row.updated_at = now
    db.commit()
    return preferences(db, member)


def _preference(db: Session, company_id: uuid.UUID, user_id: uuid.UUID, category: str) -> NotificationPreference | None:
    return db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.company_id == company_id,
            NotificationPreference.category == category,
        )
    )


class NotificationError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


def notify(
    db: Session,
    member: Member,
    *,
    category: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    dedupe_key: str | None = None,
    user_id: uuid.UUID | None = None,
    company_id: uuid.UUID | None = None,
) -> None:
    recipient = user_id or member.user.id
    company = company_id or member.company.id
    preference = _preference(db, company, recipient, category)
    send_email = mail.configured() and wants_email(db, company, recipient, category)
    if preference is not None and not preference.in_app and not send_email:
        return
    ref = f"notification:{dedupe_key}"[:80] if dedupe_key else None
    if dedupe_key is not None:
        exists = db.scalar(select(Notification.id).where(Notification.user_id == recipient, Notification.dedupe_key == dedupe_key))
        if exists is None and send_email:
            exists = db.scalar(select(EmailMessage.id).where(EmailMessage.user_id == recipient, EmailMessage.ref == ref))
        if exists is not None:
            return
    if preference is None or preference.in_app:
        db.add(
            Notification(
                company_id=company,
                user_id=recipient,
                category=category,
                title=title,
                body=body,
                link=link,
                dedupe_key=dedupe_key,
            )
        )
    if send_email:
        user = db.get(User, recipient)
        workspace = db.get(Company, company)
        if user is not None and user.status == "active" and workspace is not None:
            mail.enqueue(
                db,
                kind="notification",
                to=user.email,
                draft=mail.notification_mail(workspace.name, title, body, link),
                company_id=company,
                user_id=recipient,
                ref=ref,
            )


def list_notifications(db: Session, member: Member) -> NotificationListResponse:
    scope = (Notification.user_id == member.user.id, Notification.company_id == member.company.id)
    rows = db.scalars(select(Notification).where(*scope).order_by(Notification.created_at.desc()).limit(LIST_LIMIT))
    unread = db.scalar(select(func.count()).select_from(Notification).where(*scope, Notification.read_at.is_(None)))
    return NotificationListResponse(
        items=[
            NotificationItem(
                id=row.id,
                category=row.category,
                title=row.title,
                body=row.body,
                link=row.link,
                read=row.read_at is not None,
                created_at=row.created_at,
            )
            for row in rows
        ],
        unread=int(unread or 0),
    )


def mark_read(db: Session, member: Member, notification_id: uuid.UUID) -> NotificationListResponse:
    row = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == member.user.id,
            Notification.company_id == member.company.id,
        )
    )
    if row is None:
        raise NotificationError(404, "Bildirim bulunamadı.")
    if row.read_at is None:
        row.read_at = datetime.now(UTC)
        db.commit()
    return list_notifications(db, member)


def mark_all_read(db: Session, member: Member) -> NotificationListResponse:
    db.execute(
        update(Notification)
        .where(
            Notification.user_id == member.user.id,
            Notification.company_id == member.company.id,
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.now(UTC))
    )
    db.commit()
    return list_notifications(db, member)
