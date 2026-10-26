from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ModuleItem(BaseModel):
    key: str
    name: str
    summary: str
    requires: list[str]
    enabled: bool
    enabled_at: datetime | None = None
    company_enabled: bool = False
    access: Literal["view", "edit"] | None = None


class ModuleListResponse(BaseModel):
    modules: list[ModuleItem]


class ModuleSelectionRequest(BaseModel):
    modules: list[str] = Field(max_length=20)
