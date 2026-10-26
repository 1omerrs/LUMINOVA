import re
import secrets
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    BROWSER_SESSION_HOURS,
    REMEMBERED_SESSION_DAYS,
    dummy_password_hash,
    expiry_after,
    hash_password,
    hash_secret,
    new_secret,
    verify_password,
)
from app.models.closure import ClosureRequest
from app.models.identity import (
    AuditLog,
    Company,
    CompanyMembership,
    EmailVerificationToken,
    LoginAttempt,
    PasswordResetToken,
    Session as AuthSession,
    User,
    new_join_code,
)
from app.models.team import JoinRequest
from app.schemas.auth import CurrentUserResponse, ForgotPasswordResponse, MemberRegisterRequest, RegisterRequest, RegisterResponse
from app.services import mail

LOGIN_WINDOW = timedelta(minutes=15)
LOGIN_LIMIT = 8
# The reply is the same either way, so throttling does not reveal whether an account exists.
RESET_WINDOW = timedelta(hours=1)
RESET_LIMIT = 3
VERIFY_CODE_TTL = timedelta(minutes=30)
VERIFY_CODE_ATTEMPTS = 5
VERIFY_RESEND_GAP = timedelta(seconds=60)
VERIFY_RESEND_LIMIT = 5
_TRANSLITERATION = str.maketrans(
    {
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "ö": "o",
        "ş": "s",
        "ü": "u",
        "Ç": "c",
        "Ğ": "g",
        "İ": "i",
        "I": "i",
        "Ö": "o",
        "Ş": "s",
        "Ü": "u",
    }
)


class AuthError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


def slugify(value: str) -> str:
    text = value.translate(_TRANSLITERATION).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:48] or "sirket"


def register_account(db: Session, payload: RegisterRequest) -> RegisterResponse:
    if payload.password.lower() == payload.email.lower():
        raise AuthError(422, "Şifre e-posta adresiyle aynı olamaz.")

    existing = db.scalar(select(User.id).where(User.email == payload.email))
    if existing is not None:
        raise AuthError(409, "Bu e-posta adresiyle bir hesap zaten var.")

    user_id = uuid.uuid4()
    company_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=payload.email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        status="pending_verification",
    )
    company = Company(
        id=company_id,
        name=payload.company_name,
        slug=_available_slug(db, payload.company_name),
        owner_user_id=user_id,
        join_code=_available_code(db),
        sector=payload.sector,
        team_size=payload.team_size,
    )
    membership = CompanyMembership(company_id=company_id, user_id=user_id, role="owner")
    audit = AuditLog(
        company_id=company_id,
        actor_user_id=user_id,
        action="account.registered",
        entity_type="user",
        entity_id=str(user_id),
        summary={"company_created": True},
        source="api",
    )
    db.add(user)
    db.flush()
    db.add(company)
    db.flush()
    db.add_all([membership, audit])
    raw_token, queued = _send_verification(db, user, company_id=company_id)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if "uq_users_email" in str(error.orig):
            raise AuthError(409, "Bu e-posta adresiyle bir hesap zaten var.") from None
        raise

    settings = get_settings()
    verification_path = None
    if settings.app_env in {"local", "test"}:
        verification_path = f"/dogrula?token={raw_token}"
    return RegisterResponse(
        email_sent=False,
        email_queued=queued,
        message=(
            "Hesap oluşturuldu. 6 haneli doğrulama kodu e-posta adresinize gönderilmek üzere sıraya alındı."
            if queued
            else "Hesap oluşturuldu. E-posta servisi yapılandırılmadığı için doğrulama kodu gönderilmedi."
        ),
        verification_path=verification_path,
    )


def _available_code(db: Session) -> str:
    while True:
        code = new_join_code()
        if db.scalar(select(Company.id).where(Company.join_code == code)) is None:
            return code


def company_for_code(db: Session, code: str) -> Company:
    company = db.scalar(select(Company).where(Company.join_code == code, Company.status == "active"))
    if company is None:
        raise AuthError(404, "Bu katılım koduyla bir çalışma alanı bulunamadı. Kodu yöneticinizden kontrol edin.")
    return company


def register_member(db: Session, payload: MemberRegisterRequest) -> RegisterResponse:
    """Account for someone joining an existing company; it stays inactive until a manager approves."""
    if payload.password.lower() == payload.email.lower():
        raise AuthError(422, "Şifre e-posta adresiyle aynı olamaz.")
    company = company_for_code(db, payload.join_code)
    if db.scalar(select(User.id).where(User.email == payload.email)) is not None:
        raise AuthError(409, "Bu e-posta adresiyle bir hesap zaten var.")
    user = User(
        id=uuid.uuid4(),
        email=payload.email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        status="pending_verification",
    )
    db.add(user)
    db.flush()
    db.add(JoinRequest(company_id=company.id, user_id=user.id, position=payload.position, note=payload.note))
    db.add(
        AuditLog(
            company_id=company.id,
            actor_user_id=user.id,
            action="team.join_requested",
            entity_type="user",
            entity_id=str(user.id),
            summary={"position": payload.position} if payload.position else {},
            source="api",
        )
    )
    raw_token, queued = _send_verification(db, user)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if "uq_users_email" in str(error.orig):
            raise AuthError(409, "Bu e-posta adresiyle bir hesap zaten var.") from None
        raise
    after = f"E-postanızı doğruladıktan sonra {company.name} yöneticisi isteğinizi onaylayınca giriş yapabilirsiniz."
    return RegisterResponse(
        email_sent=False,
        email_queued=queued,
        message=(f"Katılım isteğiniz alındı. 6 haneli doğrulama kodu e-posta adresinize gönderilmek üzere sıraya alındı. {after}" if queued else f"Katılım isteğiniz alındı. {after}"),
        verification_path=f"/dogrula?token={raw_token}" if get_settings().app_env in {"local", "test"} else None,
    )


def _announce_join(db: Session, user: User) -> None:
    """Tells the managers once the person behind a join request has verified their e-mail."""
    from app.services.notifications import notify

    request = db.scalar(select(JoinRequest).where(JoinRequest.user_id == user.id, JoinRequest.status == "pending"))
    company = db.get(Company, request.company_id) if request else None
    owner = db.get(User, company.owner_user_id) if company else None
    if request is None or company is None or owner is None:
        return
    member = Member(user=owner, company=company, role="owner")
    managers = db.scalars(
        select(CompanyMembership.user_id).where(
            CompanyMembership.company_id == company.id, CompanyMembership.status == "active", CompanyMembership.role.in_(("owner", "admin"))
        )
    )
    detail = f"{request.position} olarak " if request.position else ""
    for manager_id in managers:
        notify(
            db,
            member,
            category="team",
            title=f"{user.first_name} {user.last_name} ekibe katılmak istiyor.",
            body=f"{user.email} {detail}katılım isteği gönderdi. Onaylarsanız yetkilerini seçerek ekibe ekleyebilirsiniz.",
            link="/panel/profil#ekip",
            dedupe_key=f"team.join_request:{request.id}",
            user_id=manager_id,
        )


def _new_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def _code_hash(user_id: uuid.UUID, code: str) -> str:
    return hash_secret(f"verify:{user_id}:{code}")


def _send_verification(db: Session, user: User, *, company_id: uuid.UUID | None = None) -> tuple[str, bool]:
    """Issues a link token with a six-digit code and queues the e-mail; earlier unused codes stop working."""
    now = datetime.now(UTC)
    for previous in db.scalars(
        select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id, EmailVerificationToken.used_at.is_(None))
    ):
        previous.expires_at = min(previous.expires_at, now)
    raw_token = new_secret()
    code = _new_code()
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_secret(raw_token),
            code_hash=_code_hash(user.id, code),
            expires_at=now + VERIFY_CODE_TTL,
        )
    )
    queued = mail.enqueue(
        db,
        kind="verify_email",
        to=user.email,
        draft=mail.verification_mail(user.first_name, code, raw_token, int(VERIFY_CODE_TTL.total_seconds() // 60)),
        company_id=company_id,
        user_id=user.id,
        ref=f"user:{user.id}",
    )
    return raw_token, queued is not None


def resend_verification(db: Session, email: str) -> bool:
    """Same outcome for unknown, verified and throttled addresses so the reply reveals nothing."""
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or user.email_verified_at is not None or user.status != "pending_verification":
        return False
    now = datetime.now(UTC)
    recent = list(
        db.scalars(
            select(EmailVerificationToken.created_at).where(
                EmailVerificationToken.user_id == user.id, EmailVerificationToken.created_at >= now - timedelta(hours=1)
            )
        )
    )
    if len(recent) >= VERIFY_RESEND_LIMIT or any(created >= now - VERIFY_RESEND_GAP for created in recent):
        return False
    membership = db.scalar(select(CompanyMembership.company_id).where(CompanyMembership.user_id == user.id))
    _, queued = _send_verification(db, user, company_id=membership)
    db.commit()
    return queued


def verify_code(db: Session, email: str, code: str) -> None:
    invalid = AuthError(400, "Kod hatalı veya süresi dolmuş. Yeni kod isteyebilirsiniz.")
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        raise invalid
    if user.email_verified_at is not None:
        return
    token_row = db.scalar(
        select(EmailVerificationToken)
        .where(EmailVerificationToken.user_id == user.id, EmailVerificationToken.used_at.is_(None), EmailVerificationToken.code_hash.is_not(None))
        .order_by(EmailVerificationToken.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    if token_row is None or token_row.expires_at < datetime.now(UTC):
        raise invalid
    if token_row.attempts >= VERIFY_CODE_ATTEMPTS:
        raise AuthError(429, "Çok fazla hatalı deneme yapıldı. Yeni kod isteyin.")
    if not secrets.compare_digest(token_row.code_hash or "", _code_hash(user.id, code)):
        token_row.attempts += 1
        left = VERIFY_CODE_ATTEMPTS - token_row.attempts
        db.commit()
        if left <= 0:
            raise AuthError(429, "Çok fazla hatalı deneme yapıldı. Yeni kod isteyin.")
        raise AuthError(400, f"Kod hatalı. {left} deneme hakkınız kaldı.")
    _complete_verification(db, user, token_row)


def verify_email(db: Session, raw_token: str) -> None:
    token_row = db.scalar(
        select(EmailVerificationToken).where(EmailVerificationToken.token_hash == hash_secret(raw_token)).with_for_update()
    )
    if token_row is None:
        raise AuthError(400, "Doğrulama bağlantısı geçersiz veya süresi dolmuş.")

    user = db.get(User, token_row.user_id)
    if user is None:
        raise AuthError(400, "Doğrulama bağlantısı geçersiz veya süresi dolmuş.")

    if token_row.used_at is not None:
        if user.email_verified_at is not None:
            return
        raise AuthError(400, "Doğrulama bağlantısı geçersiz veya süresi dolmuş.")

    if user.email_verified_at is not None:
        return
    if token_row.expires_at < datetime.now(UTC):
        raise AuthError(400, "Doğrulama bağlantısı geçersiz veya süresi dolmuş.")
    _complete_verification(db, user, token_row)


def _complete_verification(db: Session, user: User, token_row: EmailVerificationToken) -> None:
    now = datetime.now(UTC)
    token_row.used_at = now
    user.email_verified_at = now
    user.status = "active"
    user.updated_at = now
    _announce_join(db, user)
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="account.email_verified",
            entity_type="user",
            entity_id=str(user.id),
            summary={"verified": True},
            source="api",
        )
    )
    db.commit()


def login(db: Session, email: str, password: str, user_agent: str | None, *, remember: bool) -> str:
    normalized = email.strip().lower()
    _reject_if_rate_limited(db, normalized)
    user = db.scalar(select(User).where(User.email == normalized))
    password_ok = verify_password(password, user.password_hash if user is not None else dummy_password_hash())
    if user is None or not password_ok or user.status == "closed":
        db.add(LoginAttempt(email=normalized, succeeded=False))
        db.commit()
        raise AuthError(401, "E-posta veya şifre hatalı.")

    if user.email_verified_at is None or user.status != "active":
        db.add(LoginAttempt(email=normalized, succeeded=False))
        db.commit()
        raise AuthError(403, "E-posta adresini doğrulamanız gerekiyor.")

    active_membership = db.scalar(
        select(CompanyMembership.id)
        .join(Company, Company.id == CompanyMembership.company_id)
        .where(CompanyMembership.user_id == user.id, CompanyMembership.status == "active", Company.status == "active")
    )
    if active_membership is None and not user.is_platform_admin:
        db.add(LoginAttempt(email=normalized, succeeded=False))
        db.commit()
        raise AuthError(403, _no_membership_message(db, user))

    raw_token = new_secret()
    db.add(LoginAttempt(email=normalized, succeeded=True))
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_secret(raw_token),
            expires_at=expiry_after(days=REMEMBERED_SESSION_DAYS) if remember else expiry_after(hours=BROWSER_SESSION_HOURS),
            user_agent=(user_agent or "")[:255] or None,
        )
    )
    db.commit()
    return raw_token


def _no_membership_message(db: Session, user: User) -> str:
    request = db.scalar(select(JoinRequest).where(JoinRequest.user_id == user.id).order_by(JoinRequest.created_at.desc()))
    company = db.get(Company, request.company_id) if request else None
    if request is not None and company is not None and request.status == "pending":
        return f"Katılım isteğiniz {company.name} yöneticisinin onayını bekliyor. Onaylandığında giriş yapabilirsiniz."
    if request is not None and company is not None and request.status == "rejected":
        return f"Katılım isteğiniz {company.name} yöneticisi tarafından onaylanmadı. Ayrıntı için yöneticinizle görüşün."
    return "Bu hesabın etkin bir çalışma alanı üyeliği yok. Çalışma alanı yöneticinizle görüşün."


def logout(db: Session, raw_token: str | None) -> None:
    if raw_token is None:
        return
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_secret(raw_token)))
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(UTC)
        db.commit()


@dataclass(frozen=True)
class Member:
    user: User
    company: Company
    role: str


def resolve_member(db: Session, raw_token: str | None) -> Member:
    if raw_token is None:
        raise AuthError(401, "Oturum açmanız gerekiyor.")
    auth_session = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_secret(raw_token)))
    now = datetime.now(UTC)
    if auth_session is None or auth_session.revoked_at is not None or auth_session.expires_at < now:
        raise AuthError(401, "Oturum açmanız gerekiyor.")

    row = db.execute(
        select(User, Company, CompanyMembership.role)
        .join(CompanyMembership, CompanyMembership.user_id == User.id)
        .join(Company, Company.id == CompanyMembership.company_id)
        .where(
            User.id == auth_session.user_id,
            User.status == "active",
            CompanyMembership.status == "active",
            Company.status == "active",
        )
    ).first()
    if row is None:
        raise AuthError(401, "Oturum açmanız gerekiyor.")
    user, company, role = row
    return Member(user=user, company=company, role=role)


def resolve_staff(db: Session, raw_token: str | None) -> User:
    """The signed-in platform staff user, with or without a workspace."""
    if raw_token is None:
        raise AuthError(401, "Oturum açmanız gerekiyor.")
    auth_session = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_secret(raw_token)))
    if auth_session is None or auth_session.revoked_at is not None or auth_session.expires_at < datetime.now(UTC):
        raise AuthError(401, "Oturum açmanız gerekiyor.")
    user = db.get(User, auth_session.user_id)
    if user is None or user.status != "active":
        raise AuthError(401, "Oturum açmanız gerekiyor.")
    if not user.is_platform_admin:
        raise AuthError(403, "Bu alan yalnızca LUMINOVA ekibine açıktır.")
    return user


def current_user(db: Session, raw_token: str | None) -> CurrentUserResponse:
    try:
        member = resolve_member(db, raw_token)
    except AuthError:
        try:
            staff = resolve_staff(db, raw_token)
        except AuthError:
            raise AuthError(401, "Oturum açmanız gerekiyor.") from None
        return CurrentUserResponse(
            id=staff.id,
            first_name=staff.first_name,
            last_name=staff.last_name,
            email=staff.email,
            member_since=staff.created_at,
            role="staff",
            company_id=None,
            company_name=None,
            company_slug=None,
            company_timezone=None,
            setup_completed=True,
            is_platform_admin=True,
            staff_only=True,
        )
    profile = member_profile(member)
    profile.closure_scheduled_for = db.scalar(
        select(ClosureRequest.scheduled_for).where(ClosureRequest.company_id == member.company.id, ClosureRequest.status == "pending")
    )
    return profile


def member_profile(member: Member) -> CurrentUserResponse:
    user, company = member.user, member.company
    return CurrentUserResponse(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        member_since=user.created_at,
        role=member.role,
        company_id=company.id,
        company_name=company.name,
        company_slug=company.slug,
        company_timezone=company.timezone,
        setup_completed=company.setup_completed_at is not None,
        is_platform_admin=user.is_platform_admin,
    )


def request_password_reset(db: Session, email: str) -> ForgotPasswordResponse:
    user = db.scalar(select(User).where(User.email == email))
    reset_path = None
    recent = 0
    if user is not None:
        recent = db.scalar(
            select(func.count()).select_from(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.created_at > datetime.now(UTC) - RESET_WINDOW)
        ) or 0
    if user is not None and user.status == "active" and recent < RESET_LIMIT:
        now = datetime.now(UTC)
        open_tokens = db.scalars(
            select(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        )
        for token in open_tokens:
            token.used_at = now
        raw_token = new_secret()
        db.add(PasswordResetToken(user_id=user.id, token_hash=hash_secret(raw_token), expires_at=expiry_after(hours=1)))
        mail.enqueue(db, kind="password_reset", to=user.email, draft=mail.reset_mail(user.first_name, raw_token), user_id=user.id, ref=f"user:{user.id}")
        db.add(
            AuditLog(
                actor_user_id=user.id,
                action="account.password_reset_requested",
                entity_type="user",
                entity_id=str(user.id),
                summary={"requested": True},
                source="api",
            )
        )
        db.commit()
        if get_settings().app_env in {"local", "test"}:
            reset_path = f"/sifre-sifirla?token={raw_token}"
    channel = mail.configured()
    return ForgotPasswordResponse(
        email_sent=False,
        email_queued=channel,
        message=(
            "Bu adrese bağlı bir hesap varsa sıfırlama bağlantısı e-posta gönderim sırasına alındı. Bağlantı 1 saat geçerlidir."
            if channel
            else "Bu adrese bağlı bir hesap varsa sıfırlama bağlantısı hazırlandı. "
            "E-posta servisi yapılandırılmadığı için bağlantı e-postayla gönderilmedi."
        ),
        reset_path=reset_path,
    )


def reset_password(db: Session, raw_token: str, password: str) -> None:
    token_row = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_secret(raw_token)).with_for_update()
    )
    now = datetime.now(UTC)
    if token_row is None or token_row.used_at is not None or token_row.expires_at < now:
        raise AuthError(400, "Sıfırlama bağlantısı geçersiz veya süresi dolmuş.")
    user = db.get(User, token_row.user_id)
    if user is None or user.status != "active":
        raise AuthError(400, "Sıfırlama bağlantısı geçersiz veya süresi dolmuş.")
    if password.lower() == user.email.lower():
        raise AuthError(422, "Şifre e-posta adresiyle aynı olamaz.")

    token_row.used_at = now
    user.password_hash = hash_password(password)
    user.updated_at = now
    open_sessions = db.scalars(select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)))
    for auth_session in open_sessions:
        auth_session.revoked_at = now
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="account.password_reset",
            entity_type="user",
            entity_id=str(user.id),
            summary={"sessions_revoked": True},
            source="api",
        )
    )
    db.commit()


def _available_slug(db: Session, company_name: str) -> str:
    base = slugify(company_name)
    numbered = [base, *(f"{base}-{index}" for index in range(2, 7))]
    suffixed = [f"{base}-{secrets.token_hex(3)}" for _ in range(5)]
    for candidate in [*numbered, *suffixed]:
        exists = db.scalar(select(Company.id).where(Company.slug == candidate))
        if exists is None:
            return candidate
    raise AuthError(409, "Şirket adı için uygun bir adres üretilemedi.")


def _reject_if_rate_limited(db: Session, email: str) -> None:
    cutoff = datetime.now(UTC) - LOGIN_WINDOW
    failures = db.scalar(
        select(func.count())
        .select_from(LoginAttempt)
        .where(
            LoginAttempt.email == email,
            LoginAttempt.succeeded.is_(False),
            LoginAttempt.created_at >= cutoff,
        )
    )
    if failures is not None and int(failures) >= LOGIN_LIMIT:
        raise AuthError(429, "Çok fazla deneme yapıldı. Bir süre sonra yeniden deneyin.")
