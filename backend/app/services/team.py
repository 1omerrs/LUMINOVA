import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import expiry_after, hash_password, hash_secret, new_secret
from app.models.identity import AuditLog, Company, CompanyMembership, Session as AuthSession, User
from app.models.identity import new_join_code
from app.models.team import CompanyInvitation, JoinRequest
from app.schemas.team import (
    AcceptInvitationRequest,
    GrantableModule,
    Invitation,
    JoinDecision,
    JoinRequestItem,
    PermissionsUpdate,
    InvitationCreate,
    InvitationCreated,
    InvitationPreview,
    RoleUpdate,
    TeamMember,
    TeamResponse,
)
from app.modules.catalog import MODULES
from app.services import mail
from app.services.auth import Member
from app.services.modules import enabled_keys
from app.services.notifications import notify
from app.services.permissions import GRANTABLE, PermissionError_, describe, normalize, replace_levels, stored_levels

MANAGERS = {"owner", "admin"}
INVITATION_DAYS = 7
ROLE_LABELS = {"owner": "Sahip", "admin": "Yönetici", "member": "Üye"}
_INVALID = "Davet bağlantısı geçersiz, iptal edilmiş veya süresi dolmuş."


class TeamError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


def require_manager(member: Member) -> None:
    if member.role not in MANAGERS:
        raise TeamError(403, "Bu işlem için sahip veya yönetici olmanız gerekiyor.")


def team(db: Session, member: Member) -> TeamResponse:
    rows = db.execute(
        select(User, CompanyMembership)
        .join(CompanyMembership, CompanyMembership.user_id == User.id)
        .where(CompanyMembership.company_id == member.company.id, CompanyMembership.status == "active")
        .order_by(CompanyMembership.created_at)
    ).all()
    manager = member.role in MANAGERS
    members = [
        TeamMember(
            user_id=user.id,
            name=f"{user.first_name} {user.last_name}",
            email=user.email,
            role=row.role,
            joined_at=row.created_at,
            me=user.id == member.user.id,
            permissions=stored_levels(db, member.company.id, user.id) if row.role == "member" and (manager or user.id == member.user.id) else None,  # type: ignore[arg-type]
        )
        for user, row in rows
    ]
    invitations = []
    grantable: list[GrantableModule] = []
    requests: list[JoinRequestItem] = []
    if manager:
        invitations = [_invitation(db, item) for item in db.scalars(_open_invitations(member).order_by(CompanyInvitation.created_at.desc()))]
        enabled = enabled_keys(db, member)
        grantable = [GrantableModule(key=key, name=MODULES[key].name, requires=list(MODULES[key].requires)) for key in GRANTABLE if key in enabled]
        requests = [
            JoinRequestItem(
                id=request.id,
                name=f"{user.first_name} {user.last_name}",
                email=user.email,
                position=request.position,
                note=request.note,
                email_verified=user.email_verified_at is not None,
                created_at=request.created_at,
            )
            for request, user in db.execute(
                select(JoinRequest, User)
                .join(User, User.id == JoinRequest.user_id)
                .where(JoinRequest.company_id == member.company.id, JoinRequest.status == "pending")
                .order_by(JoinRequest.created_at)
            ).all()
        ]
    return TeamResponse(
        members=members,
        invitations=invitations,
        can_manage=manager,
        grantable=grantable,
        join_code=member.company.join_code if manager else None,
        join_requests=requests,
    )


def renew_join_code(db: Session, member: Member) -> TeamResponse:
    require_manager(member)
    company = db.scalar(select(Company).where(Company.id == member.company.id).with_for_update())
    while True:
        code = new_join_code()
        if db.scalar(select(Company.id).where(Company.join_code == code)) is None:
            break
    company.join_code = code  # type: ignore[union-attr]
    db.add(_audit(member, "team.join_code_renewed", str(member.company.id), {}))
    db.commit()
    return team(db, member)


def _pending_request(db: Session, member: Member, request_id: uuid.UUID) -> tuple[JoinRequest, User]:
    row = db.execute(
        select(JoinRequest, User)
        .join(User, User.id == JoinRequest.user_id)
        .where(JoinRequest.id == request_id, JoinRequest.company_id == member.company.id, JoinRequest.status == "pending")
        .with_for_update(of=JoinRequest)
    ).first()
    if row is None:
        raise TeamError(404, "Katılım isteği bulunamadı veya zaten karara bağlandı.")
    return row[0], row[1]


def approve_join(db: Session, member: Member, request_id: uuid.UUID, data: JoinDecision) -> TeamResponse:
    require_manager(member)
    request, user = _pending_request(db, member, request_id)
    if user.email_verified_at is None or user.status != "active":
        raise TeamError(409, "Kişi e-posta adresini henüz doğrulamadı. Doğruladıktan sonra onaylayabilirsiniz.")
    if db.scalar(select(CompanyMembership.id).where(CompanyMembership.user_id == user.id, CompanyMembership.status == "active")) is not None:
        raise TeamError(409, "Bu kişi zaten bir çalışma alanının üyesi.")
    _check_enabled(db, member, data.permissions)
    now = datetime.now(UTC)
    db.add(CompanyMembership(company_id=member.company.id, user_id=user.id, role="member"))
    try:
        levels = replace_levels(db, member.company.id, user.id, data.permissions)
    except PermissionError_ as error:
        raise TeamError(error.status_code, error.detail) from None
    request.status, request.decided_by, request.decided_at = "approved", member.user.id, now
    db.add(_audit(member, "team.join_approved", str(user.id), {"permissions": levels}))
    _tell_applicant(db, member, user, request, approved=True, levels=levels)
    db.commit()
    return team(db, member)


def reject_join(db: Session, member: Member, request_id: uuid.UUID) -> TeamResponse:
    require_manager(member)
    request, user = _pending_request(db, member, request_id)
    request.status, request.decided_by, request.decided_at = "rejected", member.user.id, datetime.now(UTC)
    db.add(_audit(member, "team.join_rejected", str(user.id), {}))
    _tell_applicant(db, member, user, request, approved=False, levels={})
    db.commit()
    return team(db, member)


def _tell_applicant(db: Session, member: Member, user: User, request: JoinRequest, *, approved: bool, levels: dict[str, str]) -> None:
    if approved:
        title = f"{member.company.name} katılım isteğinizi onayladı"
        paragraphs = [f"Merhaba {user.first_name},", f"Artık {member.company.name} çalışma alanına giriş yapabilirsiniz.", f"Erişiminiz: {describe(levels)}."]
        action = ("Giriş yap", mail.absolute("/giris"))
    else:
        title = f"{member.company.name} katılım isteğiniz hakkında"
        paragraphs = [f"Merhaba {user.first_name},", f"{member.company.name} yöneticisi katılım isteğinizi onaylamadı. Ayrıntı için yöneticinizle görüşebilirsiniz."]
        action = None
    mail.enqueue(
        db,
        kind="notification",
        to=user.email,
        draft=mail.simple_mail(title, paragraphs, action),
        company_id=member.company.id,
        user_id=user.id,
        ref=f"join:{request.id}",
    )


def set_permissions(db: Session, member: Member, user_id: uuid.UUID, data: PermissionsUpdate) -> TeamResponse:
    require_manager(member)
    membership = _membership(db, member, user_id)
    if membership.role != "member":
        raise TeamError(409, "Sahip ve yöneticiler tüm modüllere erişir; yetki yalnızca üyeler için ayarlanır.")
    _check_enabled(db, member, data.permissions)
    before = stored_levels(db, member.company.id, user_id)
    try:
        levels = replace_levels(db, member.company.id, user_id, data.permissions)
    except PermissionError_ as error:
        raise TeamError(error.status_code, error.detail) from None
    if levels != before:
        db.add(_audit(member, "team.permissions_changed", str(user_id), {"permissions": levels}))
        notify(
            db,
            member,
            category="team",
            title="Modül yetkileriniz güncellendi.",
            body=f"Erişebildikleriniz: {describe(levels)}.",
            link="/panel",
            user_id=user_id,
        )
    db.commit()
    return team(db, member)


def _check_enabled(db: Session, member: Member, grants: dict[str, str]) -> None:
    closed = [key for key in grants if key in MODULES and key not in enabled_keys(db, member)]
    if closed:
        raise TeamError(422, f"{MODULES[closed[0]].name} modülü çalışma alanında açık değil.")


def invite(db: Session, member: Member, data: InvitationCreate) -> InvitationCreated:
    require_manager(member)
    if data.role == "admin" and member.role != "owner":
        raise TeamError(403, "Yönetici davet etmeyi yalnızca çalışma alanı sahibi yapabilir.")
    if db.scalar(select(User.id).where(func.lower(User.email) == data.email)) is not None:
        raise TeamError(409, "Bu e-posta adresiyle bir LUMINOVA hesabı var. Bir hesap tek çalışma alanına üye olabilir.")
    if db.scalar(_open_invitations(member).where(func.lower(CompanyInvitation.email) == data.email)) is not None:
        raise TeamError(409, "Bu e-posta adresine gönderilmiş açık bir davet zaten var.")
    grants: dict[str, str] | None = None
    if data.role == "member":
        _check_enabled(db, member, data.permissions)
        try:
            grants = normalize(data.permissions)
        except PermissionError_ as error:
            raise TeamError(error.status_code, error.detail) from None
    raw_token = new_secret()
    invitation = CompanyInvitation(
        id=uuid.uuid4(),
        company_id=member.company.id,
        email=data.email,
        role=data.role,
        token_hash=hash_secret(raw_token),
        invited_by=member.user.id,
        expires_at=expiry_after(hours=24 * INVITATION_DAYS),
        permissions=grants,
    )
    db.add(invitation)
    db.add(_audit(member, "team.invited", str(invitation.id), {"role": data.role, **({"permissions": grants} if grants is not None else {})}))
    queued = mail.enqueue(
        db,
        kind="invitation",
        to=data.email,
        draft=mail.invitation_mail(
            member.company.name, f"{member.user.first_name} {member.user.last_name}", ROLE_LABELS[data.role].lower(), raw_token, INVITATION_DAYS
        ),
        company_id=member.company.id,
        ref=f"invitation:{invitation.id}",
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise TeamError(409, "Bu e-posta adresine gönderilmiş açık bir davet zaten var.") from None
    local = get_settings().app_env in {"local", "test"}
    return InvitationCreated(
        invitation=_invitation(db, invitation),
        email_sent=False,
        email_queued=queued is not None,
        message=(
            "Davet oluşturuldu ve davet e-postası gönderim sırasına alındı. Gönderim durumunu davet listesinden izleyebilirsiniz."
            if queued is not None
            else "Davet oluşturuldu. E-posta servisi yapılandırılmadığı için davet iletisi gönderilmedi; bağlantıyı kişiye kendiniz iletin."
        ),
        invite_path=f"/davet?token={raw_token}" if local else None,
    )


def revoke_invitation(db: Session, member: Member, invitation_id: uuid.UUID) -> None:
    require_manager(member)
    invitation = db.scalar(_open_invitations(member).where(CompanyInvitation.id == invitation_id).with_for_update())
    if invitation is None:
        raise TeamError(404, "Davet bulunamadı.")
    invitation.revoked_at = datetime.now(UTC)
    db.add(_audit(member, "team.invitation_revoked", str(invitation.id), {}))
    db.commit()


def change_role(db: Session, member: Member, user_id: uuid.UUID, data: RoleUpdate) -> TeamResponse:
    if member.role != "owner":
        raise TeamError(403, "Rolleri yalnızca çalışma alanı sahibi değiştirebilir.")
    membership = _membership(db, member, user_id)
    if membership.role == "owner":
        raise TeamError(409, "Sahibin rolü değiştirilemez.")
    if membership.role != data.role:
        previous = membership.role
        membership.role = data.role
        db.add(_audit(member, "team.role_changed", str(user_id), {"from": previous, "to": data.role}))
        db.commit()
    return team(db, member)


def remove_member(db: Session, member: Member, user_id: uuid.UUID) -> TeamResponse:
    require_manager(member)
    if user_id == member.user.id:
        raise TeamError(409, "Kendinizi çalışma alanından çıkaramazsınız.")
    membership = _membership(db, member, user_id)
    if membership.role == "owner":
        raise TeamError(409, "Çalışma alanı sahibi çıkarılamaz.")
    if membership.role == "admin" and member.role != "owner":
        raise TeamError(403, "Yöneticiyi yalnızca çalışma alanı sahibi çıkarabilir.")
    now = datetime.now(UTC)
    membership.status = "disabled"
    db.execute(update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)).values(revoked_at=now))
    db.add(_audit(member, "team.member_removed", str(user_id), {"role": membership.role}))
    db.commit()
    return team(db, member)


def preview_invitation(db: Session, raw_token: str) -> InvitationPreview:
    invitation, company = _usable(db, raw_token)
    inviter = db.get(User, invitation.invited_by) if invitation.invited_by else None
    return InvitationPreview(
        company_name=company.name,
        email=invitation.email,
        role=invitation.role,
        invited_by=f"{inviter.first_name} {inviter.last_name}" if inviter else None,
        expires_at=invitation.expires_at,
    )


def accept_invitation(db: Session, data: AcceptInvitationRequest) -> str:
    """Create the invited account and its membership; returns the email to sign in with."""
    invitation, company = _usable(db, data.token, lock=True)
    if data.password.lower() == invitation.email.lower():
        raise TeamError(422, "Şifre e-posta adresiyle aynı olamaz.")
    if db.scalar(select(User.id).where(func.lower(User.email) == invitation.email.lower())) is not None:
        raise TeamError(409, "Bu e-posta adresiyle bir LUMINOVA hesabı var. Davet kullanılamaz.")
    now = datetime.now(UTC)
    user = User(
        id=uuid.uuid4(),
        email=invitation.email.lower(),
        password_hash=hash_password(data.password),
        first_name=data.first_name,
        last_name=data.last_name,
        status="active",
        email_verified_at=now,
    )
    db.add(user)
    db.flush()
    db.add(CompanyMembership(company_id=company.id, user_id=user.id, role=invitation.role))
    if invitation.role == "member":
        replace_levels(db, company.id, user.id, invitation.permissions or {})
    invitation.accepted_at = now
    invitation.accepted_user_id = user.id
    db.add(
        AuditLog(
            company_id=company.id,
            actor_user_id=user.id,
            action="team.invitation_accepted",
            entity_type="user",
            entity_id=str(user.id),
            summary={"role": invitation.role},
            source="api",
        )
    )
    if invitation.invited_by:
        inviter = db.get(User, invitation.invited_by)
        if inviter is not None:
            notify(
                db,
                Member(user=inviter, company=company, role="owner"),
                category="team",
                title=f"{data.first_name} {data.last_name} ekibe katıldı.",
                body=f"Rol: {ROLE_LABELS[invitation.role]}.",
                link="/panel/profil#ekip",
                dedupe_key=f"team.joined:{invitation.id}",
            )
    db.commit()
    return user.email


def _usable(db: Session, raw_token: str, *, lock: bool = False) -> tuple[CompanyInvitation, Company]:
    statement = select(CompanyInvitation).where(CompanyInvitation.token_hash == hash_secret(raw_token))
    if lock:
        statement = statement.with_for_update()
    invitation = db.scalar(statement)
    if invitation is None or invitation.accepted_at is not None or invitation.revoked_at is not None or invitation.expires_at < datetime.now(UTC):
        raise TeamError(400, _INVALID)
    company = db.get(Company, invitation.company_id)
    if company is None or company.status != "active":
        raise TeamError(400, _INVALID)
    return invitation, company


def _open_invitations(member: Member):
    return select(CompanyInvitation).where(
        CompanyInvitation.company_id == member.company.id,
        CompanyInvitation.accepted_at.is_(None),
        CompanyInvitation.revoked_at.is_(None),
        CompanyInvitation.expires_at > func.now(),
    )


def _membership(db: Session, member: Member, user_id: uuid.UUID) -> CompanyMembership:
    membership = db.scalar(
        select(CompanyMembership)
        .where(CompanyMembership.company_id == member.company.id, CompanyMembership.user_id == user_id, CompanyMembership.status == "active")
        .with_for_update()
    )
    if membership is None:
        raise TeamError(404, "Ekip üyesi bulunamadı.")
    return membership


def _invitation(db: Session, item: CompanyInvitation) -> Invitation:
    inviter = db.get(User, item.invited_by) if item.invited_by else None
    message = mail.latest_status(db, [f"invitation:{item.id}"]).get(f"invitation:{item.id}")
    return Invitation(
        id=item.id,
        email=item.email,
        role=item.role,
        expires_at=item.expires_at,
        invited_by=f"{inviter.first_name} {inviter.last_name}" if inviter else None,
        created_at=item.created_at,
        email_status=message.status if message else None,  # type: ignore[arg-type]
        email_error=message.last_error if message and message.status == "failed" else None,
        permissions=item.permissions if item.role == "member" else None,  # type: ignore[arg-type]
    )


def _audit(member: Member, action: str, entity_id: str, summary: dict[str, object]) -> AuditLog:
    return AuditLog(
        company_id=member.company.id,
        actor_user_id=member.user.id,
        action=action,
        entity_type="team",
        entity_id=entity_id,
        summary=summary,
        source="api",
    )
