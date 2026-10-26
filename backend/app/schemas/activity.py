from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ActivityItem(BaseModel):
    id: UUID
    module: str
    action: str
    actor_id: UUID | None
    actor_name: str
    verb: str
    target: str | None
    detail: str | None
    link: str | None
    created_at: datetime


class ActivityActor(BaseModel):
    id: UUID
    name: str


class ActivityPage(BaseModel):
    items: list[ActivityItem]
    next_cursor: str | None
    actors: list[ActivityActor]
