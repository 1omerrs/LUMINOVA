from collections.abc import Callable

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CSRF_COOKIE, SESSION_COOKIE, secrets_match
from app.services.auth import AuthError, Member, resolve_member
from app.services.modules import ModuleError, module_access


def require_csrf(request: Request) -> None:
    header = request.headers.get("x-csrf-token")
    cookie = request.cookies.get(CSRF_COOKIE)
    if not secrets_match(header, cookie):
        raise HTTPException(status_code=403, detail="İstek doğrulanamadı.")


def current_member(request: Request, db: Session = Depends(get_db)) -> Member:
    try:
        return resolve_member(db, request.cookies.get(SESSION_COOKIE))
    except AuthError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None


READ_METHODS = {"GET", "HEAD", "OPTIONS"}


def require_module(key: str) -> Callable[..., Member]:
    """Reads need at least view access to the module; every other method needs edit access."""

    def dependency(request: Request, db: Session = Depends(get_db), member: Member = Depends(current_member)) -> Member:
        try:
            module_access(db, member, key, write=request.method not in READ_METHODS)
        except ModuleError as error:
            raise HTTPException(status_code=error.status_code, detail=error.detail) from None
        return member

    return dependency
