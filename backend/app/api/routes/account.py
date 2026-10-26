import json

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import current_member, require_csrf
from app.core.database import get_db
from app.core.security import clear_session_cookie
from app.schemas.account import ClosureInput, ClosureStatus, PasswordConfirm
from app.services import account
from app.services.auth import Member

router = APIRouter()


def _run(action):  # type: ignore[no-untyped-def]
    try:
        return action()
    except account.AccountError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None


@router.post("/exports/workspace")
def export_workspace(
    db: Session = Depends(get_db),
    member: Member = Depends(current_member),
    _: None = Depends(require_csrf),
) -> Response:
    name, content = _run(lambda: account.workspace_export(db, member))
    return Response(content=content, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/me/export")
def export_me(db: Session = Depends(get_db), member: Member = Depends(current_member)) -> Response:
    data = account.personal_export(db, member)
    body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    return Response(content=body, media_type="application/json", headers={"Content-Disposition": 'attachment; filename="luminova-kisisel-verilerim.json"'})


@router.get("/workspace/closure", response_model=ClosureStatus | None)
def read_closure(db: Session = Depends(get_db), member: Member = Depends(current_member)) -> ClosureStatus | None:
    request = account.pending_closure(db, member.company.id)
    if request is None:
        return None
    return ClosureStatus(id=request.id, scheduled_for=request.scheduled_for, created_at=request.created_at, reason=request.reason)


@router.post("/workspace/closure", response_model=ClosureStatus, status_code=201)
def open_closure(
    payload: ClosureInput,
    db: Session = Depends(get_db),
    member: Member = Depends(current_member),
    _: None = Depends(require_csrf),
) -> ClosureStatus:
    request = _run(lambda: account.request_closure(db, member, payload.password, payload.reason))
    return ClosureStatus(id=request.id, scheduled_for=request.scheduled_for, created_at=request.created_at, reason=request.reason)


@router.delete("/workspace/closure", status_code=204)
def cancel_closure(
    db: Session = Depends(get_db),
    member: Member = Depends(current_member),
    _: None = Depends(require_csrf),
) -> Response:
    _run(lambda: account.cancel_closure(db, member))
    return Response(status_code=204)


@router.post("/me/close", status_code=204)
def close_me(
    payload: PasswordConfirm,
    db: Session = Depends(get_db),
    member: Member = Depends(current_member),
    _: None = Depends(require_csrf),
) -> Response:
    _run(lambda: account.close_own_account(db, member, payload.password))
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response
