from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PasswordConfirm(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class ClosureInput(PasswordConfirm):
    reason: str | None = Field(default=None, max_length=1000)


class ClosureStatus(BaseModel):
    id: UUID
    scheduled_for: datetime
    created_at: datetime
    reason: str | None


class AdminClosure(BaseModel):
    id: UUID
    company_id: UUID
    company_name: str
    company_slug: str
    requested_by: str
    requested_email: str
    reason: str | None
    scheduled_for: datetime
    created_at: datetime
    due: bool
