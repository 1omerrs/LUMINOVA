import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import current_member, require_csrf
from app.core.database import get_db
from app.schemas.notifications import NotificationListResponse, PreferenceItem, PreferenceUpdate
from app.services.auth import Member
from app.services.notifications import NotificationError, list_notifications, mark_all_read, mark_read, preferences, update_preferences
from app.services.insights import sync_tasks
from app.services.reminders import generate_reminders

router = APIRouter(prefix="/notifications")
logger = logging.getLogger(__name__)


@router.get("", response_model=NotificationListResponse)
def read_notifications(db: Session = Depends(get_db), member: Member = Depends(current_member)) -> NotificationListResponse:
    generate_reminders(db, member)
    if member.company.setup_completed_at is not None:
        try:
            sync_tasks(db, member)
        except Exception:
            db.rollback()
            logger.exception("Automatic task sync failed for company %s", member.company.id)
    return list_notifications(db, member)


@router.get("/preferences", response_model=list[PreferenceItem])
def read_preferences(db: Session = Depends(get_db), member: Member = Depends(current_member)) -> list[PreferenceItem]:
    return preferences(db, member)


@router.put("/preferences", response_model=list[PreferenceItem])
def change_preferences(
    payload: PreferenceUpdate,
    db: Session = Depends(get_db),
    member: Member = Depends(current_member),
    _: None = Depends(require_csrf),
) -> list[PreferenceItem]:
    try:
        return update_preferences(db, member, payload.in_app, payload.email)
    except NotificationError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None


@router.post("/read-all", response_model=NotificationListResponse)
def read_all(
    db: Session = Depends(get_db),
    member: Member = Depends(current_member),
    _: None = Depends(require_csrf),
) -> NotificationListResponse:
    return mark_all_read(db, member)


@router.post("/{notification_id}/read", response_model=NotificationListResponse)
def read_one(
    notification_id: UUID,
    db: Session = Depends(get_db),
    member: Member = Depends(current_member),
    _: None = Depends(require_csrf),
) -> NotificationListResponse:
    try:
        return mark_read(db, member, notification_id)
    except NotificationError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None
