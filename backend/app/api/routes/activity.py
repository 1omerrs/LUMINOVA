from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import current_member
from app.core.database import get_db
from app.schemas.activity import ActivityActor, ActivityItem, ActivityPage
from app.services.activity import PAGE_SIZE, ActivityError, list_activity
from app.services.auth import Member

router = APIRouter(prefix="/activity")


@router.get("", response_model=ActivityPage)
def read_activity(
    module: str | None = Query(default=None),
    actor: UUID | None = Query(default=None),
    cursor: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=PAGE_SIZE, ge=1, le=50),
    db: Session = Depends(get_db),
    member: Member = Depends(current_member),
) -> ActivityPage:
    if member.company.setup_completed_at is None:
        raise HTTPException(status_code=403, detail="Önce çalışma alanı kurulumunu tamamlayın.")
    try:
        items, next_cursor, actors = list_activity(db, member, module=module, actor=actor, cursor=cursor, limit=limit)
    except ActivityError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None
    return ActivityPage(
        items=[ActivityItem.model_validate(item) for item in items],
        next_cursor=next_cursor,
        actors=[ActivityActor.model_validate(actor) for actor in actors],
    )
