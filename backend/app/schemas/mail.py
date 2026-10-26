from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

MailStatus = Literal["queued", "handed_off", "sent", "failed"]


class MailItem(BaseModel):
    id: UUID
    kind: str
    kind_label: str
    to_email: str
    subject: str
    company_name: str | None
    status: MailStatus
    attempts: int
    last_error: str | None
    provider_message_id: str | None
    retryable: bool
    created_at: datetime
    handed_off_at: datetime | None
    sent_at: datetime | None


class MailList(BaseModel):
    configured: bool
    webhook_host: str | None
    counts: dict[str, int]
    items: list[MailItem]


class MailCallbackResult(BaseModel):
    ok: bool
    id: UUID
    status: MailStatus
