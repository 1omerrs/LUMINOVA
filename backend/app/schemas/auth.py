from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


def _clean_text(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned or any(ord(character) < 32 for character in cleaned):
        raise ValueError("Geçersiz karakter")
    return cleaned


class RegisterRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    company_name: str = Field(min_length=2, max_length=160)
    sector: str | None = Field(default=None, max_length=40)
    team_size: str | None = Field(default=None, max_length=16)

    @field_validator("sector")
    @classmethod
    def known_sector(cls, value: str | None) -> str | None:
        if value and value not in SECTORS:
            raise ValueError("Sektör listeden seçilmeli.")
        return value or None

    @field_validator("team_size")
    @classmethod
    def known_size(cls, value: str | None) -> str | None:
        if value and value not in TEAM_SIZES:
            raise ValueError("Ekip büyüklüğü listeden seçilmeli.")
        return value or None

    @field_validator("first_name", "last_name", "company_name")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return _clean_text(value)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


SECTORS = ("uretim", "perakende", "hizmet", "insaat", "gida", "tekstil", "mobilya", "teknoloji", "saglik", "diger")
TEAM_SIZES = ("1", "2-5", "6-20", "21-50", "51+")


class MemberRegisterRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    join_code: str = Field(min_length=8, max_length=16)
    position: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=300)

    @field_validator("first_name", "last_name")
    @classmethod
    def clean_names(cls, value: str) -> str:
        return _clean_text(value)

    @field_validator("position", "note")
    @classmethod
    def clean_optional(cls, value: str | None) -> str | None:
        return _clean_text(value) if value and value.strip() else None

    @field_validator("email")
    @classmethod
    def lower_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("join_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return normalize_join_code(value)


def normalize_join_code(value: str) -> str:
    raw = "".join(character for character in value.upper() if character.isalnum())
    return f"{raw[:4]}-{raw[4:]}" if len(raw) == 8 else value.strip().upper()


class JoinPreview(BaseModel):
    company_name: str


class LoginRequest(BaseModel):
    # Usually an e-mail address; the platform staff account may use a short login name.
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)
    remember: bool = False

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=20, max_length=256)


class VerifyCodeRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    code: str = Field(pattern=r"^\d{6}$")

    @field_validator("code", mode="before")
    @classmethod
    def strip_code(cls, value: object) -> object:
        return value.replace(" ", "").strip() if isinstance(value, str) else value


class ResendCodeRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    password: str = Field(min_length=10, max_length=128)


class RegisterResponse(BaseModel):
    email_sent: bool
    email_queued: bool = False
    message: str
    verification_path: str | None = None


class ForgotPasswordResponse(BaseModel):
    email_sent: bool
    email_queued: bool = False
    message: str
    reset_path: str | None = None


class MessageResponse(BaseModel):
    message: str


class CsrfResponse(BaseModel):
    token: str


class CurrentUserResponse(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    email: str
    member_since: datetime
    # Company fields are empty only for the platform staff account, which belongs to no workspace.
    role: str
    company_id: UUID | None
    company_name: str | None
    company_slug: str | None
    company_timezone: str | None
    setup_completed: bool
    is_platform_admin: bool = False
    staff_only: bool = False
    closure_scheduled_for: datetime | None = None
