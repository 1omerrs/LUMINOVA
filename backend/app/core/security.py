import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Response

from app.core.config import get_settings

SESSION_COOKIE = "luminova_session"
CSRF_COOKIE = "luminova_csrf"
REMEMBERED_SESSION_DAYS = 30
BROWSER_SESSION_HOURS = 12
CSRF_HOURS = 4

_hasher: PasswordHasher | None = None
_dummy_hash: str | None = None


def get_password_hasher() -> PasswordHasher:
    global _hasher
    if _hasher is None:
        if get_settings().app_env == "test":
            _hasher = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)
        else:
            _hasher = PasswordHasher()
    return _hasher


def hash_password(password: str) -> str:
    return get_password_hasher().hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return get_password_hasher().verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def dummy_password_hash() -> str:
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("luminova-timing-placeholder")
    return _dummy_hash


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def hash_secret(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def secrets_match(left: str | None, right: str | None) -> bool:
    if left is None or right is None or not left or not right:
        return False
    return secrets.compare_digest(left, right)


def expiry_after(*, days: int = 0, hours: int = 0) -> datetime:
    return datetime.now(UTC) + timedelta(days=days, hours=hours)


def cookie_secure() -> bool:
    return get_settings().app_env == "production"


def set_session_cookie(response: Response, raw_token: str, *, remember: bool) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=raw_token,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        max_age=REMEMBERED_SESSION_DAYS * 24 * 60 * 60 if remember else None,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def set_csrf_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=CSRF_COOKIE,
        value=raw_token,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        max_age=CSRF_HOURS * 60 * 60,
        path="/",
    )
