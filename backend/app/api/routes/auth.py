from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import require_csrf
from app.core.database import get_db
from app.core.security import (
    SESSION_COOKIE,
    clear_session_cookie,
    new_secret,
    set_csrf_cookie,
    set_session_cookie,
)
from app.schemas.auth import (
    CsrfResponse,
    CurrentUserResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    JoinPreview,
    LoginRequest,
    MemberRegisterRequest,
    MessageResponse,
    RegisterRequest,
    RegisterResponse,
    ResendCodeRequest,
    ResetPasswordRequest,
    VerifyCodeRequest,
    VerifyEmailRequest,
    normalize_join_code,
)
from app.services.auth import (
    AuthError,
    company_for_code,
    current_user,
    login,
    logout,
    register_account,
    register_member,
    request_password_reset,
    resend_verification,
    reset_password,
    verify_code,
    verify_email,
)

router = APIRouter(prefix="/auth")


def _raise_auth(error: AuthError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.detail)


@router.get("/csrf", response_model=CsrfResponse)
def read_csrf(response: Response) -> CsrfResponse:
    token = new_secret()
    set_csrf_cookie(response, token)
    return CsrfResponse(token=token)


@router.post("/register", response_model=RegisterResponse, status_code=201)
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_csrf),
) -> RegisterResponse:
    try:
        return register_account(db, payload)
    except AuthError as error:
        _raise_auth(error)


@router.get("/join/preview", response_model=JoinPreview)
def join_preview(code: str = Query(min_length=8, max_length=16), db: Session = Depends(get_db)) -> JoinPreview:
    try:
        return JoinPreview(company_name=company_for_code(db, normalize_join_code(code)).name)
    except AuthError as error:
        _raise_auth(error)


@router.post("/register/member", response_model=RegisterResponse, status_code=201)
def register_as_member(
    payload: MemberRegisterRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_csrf),
) -> RegisterResponse:
    try:
        return register_member(db, payload)
    except AuthError as error:
        _raise_auth(error)


@router.post("/verify-email", response_model=MessageResponse)
def verify(
    payload: VerifyEmailRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_csrf),
) -> MessageResponse:
    try:
        verify_email(db, payload.token)
    except AuthError as error:
        _raise_auth(error)
    return MessageResponse(message="E-posta adresiniz doğrulandı.")


@router.post("/verify-code", response_model=MessageResponse)
def verify_with_code(
    payload: VerifyCodeRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_csrf),
) -> MessageResponse:
    try:
        verify_code(db, payload.email, payload.code)
    except AuthError as error:
        _raise_auth(error)
    return MessageResponse(message="E-posta adresiniz doğrulandı.")


@router.post("/verify-code/resend", response_model=MessageResponse, status_code=202)
def resend_code(
    payload: ResendCodeRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_csrf),
) -> MessageResponse:
    resend_verification(db, payload.email)
    return MessageResponse(
        message="Hesabınız doğrulama bekliyorsa yeni kod e-posta adresinize gönderilmek üzere sıraya alındı. Yeni kod en fazla dakikada bir istenebilir."
    )


@router.post("/login", response_model=CurrentUserResponse)
def sign_in(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    _: None = Depends(require_csrf),
) -> CurrentUserResponse:
    try:
        raw_token = login(db, payload.email, payload.password, request.headers.get("user-agent"), remember=payload.remember)
    except AuthError as error:
        _raise_auth(error)
    set_session_cookie(response, raw_token, remember=payload.remember)
    return current_user(db, raw_token)


@router.post("/logout", status_code=204)
def sign_out(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    _: None = Depends(require_csrf),
) -> Response:
    logout(db, request.cookies.get(SESSION_COOKIE))
    clear_session_cookie(response)
    return Response(status_code=204)


@router.post("/forgot-password", response_model=ForgotPasswordResponse, status_code=202)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_csrf),
) -> ForgotPasswordResponse:
    return request_password_reset(db, payload.email)


@router.post("/reset-password", response_model=MessageResponse)
def change_forgotten_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_csrf),
) -> MessageResponse:
    try:
        reset_password(db, payload.token, payload.password)
    except AuthError as error:
        _raise_auth(error)
    return MessageResponse(message="Şifreniz güncellendi. Yeni şifrenizle giriş yapabilirsiniz.")


@router.get("/me", response_model=CurrentUserResponse)
def me(request: Request, db: Session = Depends(get_db)) -> CurrentUserResponse:
    try:
        return current_user(db, request.cookies.get(SESSION_COOKIE))
    except AuthError as error:
        _raise_auth(error)
