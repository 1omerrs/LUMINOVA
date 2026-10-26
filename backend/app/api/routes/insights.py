from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_member, require_csrf
from app.core.database import get_db
from app.models.identity import CompanyMembership
from app.services import insights
from app.services.auth import Member

router = APIRouter()


class InsightItem(BaseModel):
    key: str
    kind: str
    module: str
    severity: Literal["high", "medium", "low"]
    title: str
    detail: str
    link: str
    task_id: UUID | None
    task_assignee: str | None


class InsightList(BaseModel):
    items: list[InsightItem]
    autopilot: bool


class KindOption(BaseModel):
    key: str
    module: str
    label: str
    on: bool


class AutopilotOut(BaseModel):
    enabled: bool
    default_assignee_id: UUID | None
    kinds: list[KindOption]
    last_run_at: datetime | None


class AutopilotInput(BaseModel):
    enabled: bool
    kinds: list[str] = Field(default_factory=list, max_length=20)
    default_assignee_id: UUID | None = None


class RunResult(BaseModel):
    created: int
    resolved: int


def _out(config) -> AutopilotOut:  # type: ignore[no-untyped-def]
    chosen = set(config.kinds)
    return AutopilotOut(
        enabled=config.enabled,
        default_assignee_id=config.default_assignee_id,
        kinds=[KindOption(key=key, module=module, label=label, on=key in chosen) for key, (module, label) in insights.KINDS.items()],
        last_run_at=config.last_run_at,
    )


@router.get("/insights", response_model=InsightList)
def read_insights(db: Session = Depends(get_db), member: Member = Depends(current_member)) -> InsightList:
    insights.sync_tasks(db, member)
    return InsightList.model_validate(insights.describe(db, member))


@router.get("/autopilot", response_model=AutopilotOut)
def read_autopilot(db: Session = Depends(get_db), member: Member = Depends(current_member)) -> AutopilotOut:
    config = insights.settings(db, member)
    db.commit()
    return _out(config)


@router.put("/autopilot", response_model=AutopilotOut)
def change_autopilot(
    payload: AutopilotInput,
    db: Session = Depends(get_db),
    member: Member = Depends(current_member),
    _: None = Depends(require_csrf),
) -> AutopilotOut:
    if member.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Otomatik görev ayarlarını yalnızca şirket sahibi veya yönetici değiştirebilir.")
    unknown = set(payload.kinds) - set(insights.KINDS)
    if unknown:
        raise HTTPException(status_code=422, detail="Bilinmeyen görev türü seçildi.")
    if payload.default_assignee_id is not None and db.scalar(
        select(CompanyMembership.user_id).where(
            CompanyMembership.company_id == member.company.id,
            CompanyMembership.user_id == payload.default_assignee_id,
            CompanyMembership.status == "active",
        )
    ) is None:
        raise HTTPException(status_code=422, detail="Seçilen kişi bu çalışma alanında değil.")
    config = insights.settings(db, member)
    config.enabled = payload.enabled
    config.kinds = [key for key in insights.KINDS if key in set(payload.kinds)]
    config.default_assignee_id = payload.default_assignee_id
    config.last_run_at = None
    db.commit()
    insights.sync_tasks(db, member, force=True)
    return _out(insights.settings(db, member))


@router.post("/autopilot/run", response_model=RunResult)
def run_autopilot(db: Session = Depends(get_db), member: Member = Depends(current_member), _: None = Depends(require_csrf)) -> RunResult:
    return RunResult(**insights.sync_tasks(db, member, force=True))
