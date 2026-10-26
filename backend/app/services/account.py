"""Data export, workspace closure requests and personal account closure."""

import csv
import io
import json
import uuid
import zipfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Table, select, update
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.db.base import Base
from app.models.closure import ClosureRequest
from app.models.identity import AuditLog, Company, CompanyMembership, User
from app.models.identity import Session as AuthSession
from app.models.notifications import Notification
from app.models.support import SupportTicket
from app.modules.tasks.models import Task
from app.services.auth import Member
from app.services.notifications import notify

GRACE_DAYS = 30
EXPORT_TABLES: tuple[tuple[str, str], ...] = (
    ("customers", "musteriler"),
    ("products", "urunler"),
    ("stock_movements", "stok_hareketleri"),
    ("orders", "siparisler"),
    ("order_items", "siparis_kalemleri"),
    ("order_status_events", "siparis_durumlari"),
    ("quotes", "teklifler"),
    ("quote_items", "teklif_kalemleri"),
    ("tasks", "gorevler"),
    ("projects", "projeler"),
    ("project_milestones", "proje_asamalari"),
    ("financial_records", "finans_kayitlari"),
    ("financial_record_revisions", "finans_revizyonlari"),
    ("production_orders", "is_emirleri"),
    ("production_materials", "is_emri_malzemeleri"),
    ("support_tickets", "destek_talepleri"),
    ("support_messages", "destek_mesajlari"),
    ("audit_logs", "etkinlikler"),
)
README = """LUMINOVA çalışma alanı dışa aktarımı

Şirket: {company}
Oluşturulma: {created} (UTC)
Oluşturan: {actor}

Her tablo ayrı bir CSV dosyasıdır. Dosyalar UTF-8 (BOM'lu) kodlanmıştır ve
alan ayracı noktalı virgüldür (;), böylece Excel Türkçe ayarlarla doğrudan açar.
Ondalık sayılar virgülle (12,50), tarih ve saatler ISO 8601 biçimiyle yazılır.
Sütun adları veritabanındaki adlardır; kimlik sütunları (id, *_id) dosyalar
arasında ilişki kurmak için kullanılır.

uyeler.csv çalışma alanı üyelerini içerir; şifreler ve oturum bilgileri
dışa aktarılmaz. Webhook anahtarları ve kişisel bildirimler bu pakette yoktur.
"""


class AccountError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text.replace(".", ",")
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _csv(header: list[str], rows: list[list[object]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([_cell(value) for value in row])
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def _require_manager(member: Member) -> None:
    if member.role not in {"owner", "admin"}:
        raise AccountError(403, "Çalışma alanı verilerini sahip veya yönetici indirebilir.")


def workspace_export(db: Session, member: Member) -> tuple[str, bytes]:
    _require_manager(member)
    now = datetime.now(UTC)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(
            "BENIOKU.txt",
            README.format(company=member.company.name, created=now.strftime("%Y-%m-%d %H:%M"), actor=f"{member.user.first_name} {member.user.last_name}"),
        )
        for table_name, file_name in EXPORT_TABLES:
            table: Table = Base.metadata.tables[table_name]
            columns = [column for column in table.columns if column.name != "company_id"]
            order = [table.c.created_at] if "created_at" in table.c else []
            rows = db.execute(select(*columns).where(table.c.company_id == member.company.id).order_by(*order, table.c.id)).all()
            bundle.writestr(f"{file_name}.csv", _csv([column.name for column in columns], [list(row) for row in rows]))
        members = db.execute(
            select(User.id, User.first_name, User.last_name, User.email, CompanyMembership.role, CompanyMembership.status, CompanyMembership.created_at)
            .join(CompanyMembership, CompanyMembership.user_id == User.id)
            .where(CompanyMembership.company_id == member.company.id)
            .order_by(CompanyMembership.created_at)
        ).all()
        bundle.writestr("uyeler.csv", _csv(["user_id", "first_name", "last_name", "email", "role", "status", "joined_at"], [list(row) for row in members]))
    db.add(
        AuditLog(
            company_id=member.company.id,
            actor_user_id=member.user.id,
            action="workspace.exported",
            entity_type="company",
            entity_id=str(member.company.id),
            summary={"tables": len(EXPORT_TABLES) + 1},
            source="api",
        )
    )
    db.commit()
    return f"luminova-{member.company.slug}-{now.strftime('%Y%m%d-%H%M')}.zip", archive.getvalue()


def personal_export(db: Session, member: Member) -> dict[str, object]:
    user = member.user
    memberships = db.execute(
        select(Company.name, CompanyMembership.role, CompanyMembership.status, CompanyMembership.created_at)
        .join(Company, Company.id == CompanyMembership.company_id)
        .where(CompanyMembership.user_id == user.id)
    ).all()
    notifications = db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at)).all()
    tasks = db.scalars(select(Task).where(Task.assignee_user_id == user.id, Task.deleted_at.is_(None)).order_by(Task.created_at)).all()
    tickets = db.scalars(select(SupportTicket).where(SupportTicket.created_by == user.id).order_by(SupportTicket.created_at)).all()
    db.add(
        AuditLog(
            company_id=member.company.id,
            actor_user_id=user.id,
            action="account.data_exported",
            entity_type="user",
            entity_id=str(user.id),
            summary={},
            source="api",
        )
    )
    db.commit()
    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "profile": {
            "id": str(user.id),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "status": user.status,
            "email_verified_at": _cell(user.email_verified_at) or None,
            "created_at": user.created_at.isoformat(),
        },
        "memberships": [{"company": name, "role": role, "status": status, "joined_at": joined.isoformat()} for name, role, status, joined in memberships],
        "assigned_tasks": [{"title": task.title, "status": task.status, "due_date": _cell(task.due_date) or None} for task in tasks],
        "support_tickets": [{"subject": ticket.subject, "status": ticket.status, "created_at": ticket.created_at.isoformat()} for ticket in tickets],
        "notifications": [
            {"category": row.category, "title": row.title, "body": row.body, "read": row.read_at is not None, "created_at": row.created_at.isoformat()}
            for row in notifications
        ],
    }


def pending_closure(db: Session, company_id: uuid.UUID) -> ClosureRequest | None:
    return db.scalar(select(ClosureRequest).where(ClosureRequest.company_id == company_id, ClosureRequest.status == "pending"))


def _check_password(member: Member, password: str) -> None:
    if not verify_password(password, member.user.password_hash):
        raise AccountError(403, "Şifre doğru değil.")


def _audit(member: Member, action: str, request: ClosureRequest) -> AuditLog:
    return AuditLog(
        company_id=request.company_id,
        actor_user_id=member.user.id,
        action=action,
        entity_type="closure_request",
        entity_id=str(request.id),
        summary={"scheduled_for": request.scheduled_for.isoformat()},
        source="api",
    )


def request_closure(db: Session, member: Member, password: str, reason: str | None) -> ClosureRequest:
    if member.role != "owner":
        raise AccountError(403, "Çalışma alanını yalnızca sahibi kapatabilir.")
    _check_password(member, password)
    if pending_closure(db, member.company.id) is not None:
        raise AccountError(409, "Bu çalışma alanı için zaten bekleyen bir kapatma talebi var.")
    now = datetime.now(UTC)
    request = ClosureRequest(
        company_id=member.company.id,
        requested_by=member.user.id,
        reason=(reason or "").strip()[:1000] or None,
        status="pending",
        scheduled_for=now + timedelta(days=GRACE_DAYS),
        created_at=now,
    )
    db.add(request)
    db.flush()
    db.add(_audit(member, "workspace.closure_requested", request))
    admins = db.scalars(
        select(CompanyMembership.user_id).where(
            CompanyMembership.company_id == member.company.id,
            CompanyMembership.status == "active",
            CompanyMembership.role == "admin",
        )
    ).all()
    for user_id in admins:
        notify(
            db,
            member,
            category="workspace",
            title="Çalışma alanı için kapatma talebi açıldı.",
            body=f"{member.user.first_name} {member.user.last_name} talebi açtı. Planlanan kapanış {request.scheduled_for:%d.%m.%Y}.",
            link="/panel/profil#veri",
            user_id=user_id,
        )
    db.commit()
    return request


def cancel_closure(db: Session, member: Member) -> None:
    if member.role != "owner":
        raise AccountError(403, "Kapatma talebini yalnızca sahibi iptal edebilir.")
    request = pending_closure(db, member.company.id)
    if request is None:
        raise AccountError(404, "Bekleyen kapatma talebi yok.")
    request.status = "cancelled"
    request.cancelled_at = datetime.now(UTC)
    db.add(_audit(member, "workspace.closure_cancelled", request))
    db.commit()


def close_own_account(db: Session, member: Member, password: str) -> None:
    if member.role == "owner":
        raise AccountError(409, "Çalışma alanı sahibi hesabını kapatamaz. Önce çalışma alanını kapatma talebi açın.")
    _check_password(member, password)
    now = datetime.now(UTC)
    user = member.user
    user.status = "closed"
    user.updated_at = now
    db.execute(update(CompanyMembership).where(CompanyMembership.user_id == user.id).values(status="disabled"))
    db.execute(update(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)).values(revoked_at=now))
    db.add(
        AuditLog(
            company_id=member.company.id,
            actor_user_id=user.id,
            action="account.closed",
            entity_type="user",
            entity_id=str(user.id),
            summary={"role": member.role},
            source="api",
        )
    )
    db.commit()


def list_closures(db: Session) -> list[dict[str, object]]:
    rows = db.execute(
        select(ClosureRequest, Company.name, Company.slug, User.first_name, User.last_name, User.email)
        .join(Company, Company.id == ClosureRequest.company_id)
        .join(User, User.id == ClosureRequest.requested_by)
        .where(ClosureRequest.status == "pending")
        .order_by(ClosureRequest.scheduled_for)
    ).all()
    return [
        {
            "id": request.id,
            "company_id": request.company_id,
            "company_name": name,
            "company_slug": slug,
            "requested_by": f"{first} {last}",
            "requested_email": email,
            "reason": request.reason,
            "scheduled_for": request.scheduled_for,
            "created_at": request.created_at,
            "due": request.scheduled_for <= datetime.now(UTC),
        }
        for request, name, slug, first, last, email in rows
    ]


def complete_closure(db: Session, staff: Member, request_id: uuid.UUID) -> None:
    request = db.scalar(select(ClosureRequest).where(ClosureRequest.id == request_id).with_for_update())
    if request is None or request.status != "pending":
        raise AccountError(404, "Bekleyen kapatma talebi bulunamadı.")
    now = datetime.now(UTC)
    company = db.get(Company, request.company_id)
    if company is None:
        raise AccountError(404, "Çalışma alanı bulunamadı.")
    company.status = "closed"
    company.updated_at = now
    members = db.scalars(select(CompanyMembership.user_id).where(CompanyMembership.company_id == company.id)).all()
    db.execute(update(CompanyMembership).where(CompanyMembership.company_id == company.id).values(status="disabled"))
    if members:
        db.execute(update(AuthSession).where(AuthSession.user_id.in_(members), AuthSession.revoked_at.is_(None)).values(revoked_at=now))
    request.status = "completed"
    request.completed_at = now
    request.completed_by = staff.user.id
    db.add(
        AuditLog(
            company_id=company.id,
            actor_user_id=staff.user.id,
            action="admin.workspace_closed",
            entity_type="company",
            entity_id=str(company.id),
            summary={"request": str(request.id)},
            source="admin",
        )
    )
    db.commit()
