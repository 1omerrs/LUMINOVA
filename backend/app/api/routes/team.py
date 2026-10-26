from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import current_member, require_csrf
from app.core.database import get_db
from app.core.security import set_session_cookie
from app.schemas.auth import CurrentUserResponse
from app.schemas.team import (
    AcceptInvitationRequest,
    InvitationCreate,
    InvitationCreated,
    InvitationPreview,
    JoinDecision,
    PermissionsUpdate,
    RoleUpdate,
    TeamResponse,
)
from app.services.auth import AuthError, current_user, login
from app.services.auth import Member
from app.services.team import (
    TeamError,
    accept_invitation,
    approve_join,
    change_role,
    reject_join,
    renew_join_code,
    invite,
    preview_invitation,
    remove_member,
    revoke_invitation,
    set_permissions,
    team,
)

router = APIRouter()


def _raise(error: TeamError | AuthError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.detail)


@router.get("/team", response_model=TeamResponse)
def read_team(db: Session = Depends(get_db), member: Member = Depends(current_member)) -> TeamResponse:
    return team(db, member)


@router.post("/team/invitations", response_model=InvitationCreated, status_code=201)
def create_invitation(
    payload: InvitationCreate, db: Session = Depends(get_db), member: Member = Depends(current_member), _: None = Depends(require_csrf)
) -> InvitationCreated:
    try:
        return invite(db, member, payload)
    except TeamError as error:
        _raise(error)


@router.delete("/team/invitations/{invitation_id}", status_code=204)
def delete_invitation(invitation_id: UUID, db: Session = Depends(get_db), member: Member = Depends(current_member), _: None = Depends(require_csrf)) -> Response:
    try:
        revoke_invitation(db, member, invitation_id)
    except TeamError as error:
        _raise(error)
    return Response(status_code=204)


@router.put("/team/members/{user_id}", response_model=TeamResponse)
def update_member(
    user_id: UUID, payload: RoleUpdate, db: Session = Depends(get_db), member: Member = Depends(current_member), _: None = Depends(require_csrf)
) -> TeamResponse:
    try:
        return change_role(db, member, user_id, payload)
    except TeamError as error:
        _raise(error)


@router.put("/team/members/{user_id}/permissions", response_model=TeamResponse)
def update_permissions(
    user_id: UUID, payload: PermissionsUpdate, db: Session = Depends(get_db), member: Member = Depends(current_member), _: None = Depends(require_csrf)
) -> TeamResponse:
    try:
        return set_permissions(db, member, user_id, payload)
    except TeamError as error:
        _raise(error)


@router.post("/team/join-code", response_model=TeamResponse)
def renew_code(db: Session = Depends(get_db), member: Member = Depends(current_member), _: None = Depends(require_csrf)) -> TeamResponse:
    try:
        return renew_join_code(db, member)
    except TeamError as error:
        _raise(error)


@router.post("/team/join-requests/{request_id}/approve", response_model=TeamResponse)
def approve(
    request_id: UUID, payload: JoinDecision, db: Session = Depends(get_db), member: Member = Depends(current_member), _: None = Depends(require_csrf)
) -> TeamResponse:
    try:
        return approve_join(db, member, request_id, payload)
    except TeamError as error:
        _raise(error)


@router.post("/team/join-requests/{request_id}/reject", response_model=TeamResponse)
def reject(request_id: UUID, db: Session = Depends(get_db), member: Member = Depends(current_member), _: None = Depends(require_csrf)) -> TeamResponse:
    try:
        return reject_join(db, member, request_id)
    except TeamError as error:
        _raise(error)


@router.delete("/team/members/{user_id}", response_model=TeamResponse)
def delete_member(user_id: UUID, db: Session = Depends(get_db), member: Member = Depends(current_member), _: None = Depends(require_csrf)) -> TeamResponse:
    try:
        return remove_member(db, member, user_id)
    except TeamError as error:
        _raise(error)


@router.get("/auth/invitations/preview", response_model=InvitationPreview)
def read_invitation(token: str = Query(min_length=10, max_length=200), db: Session = Depends(get_db)) -> InvitationPreview:
    try:
        return preview_invitation(db, token)
    except TeamError as error:
        _raise(error)


@router.post("/auth/invitations/accept", response_model=CurrentUserResponse, status_code=201)
def join(
    payload: AcceptInvitationRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    _: None = Depends(require_csrf),
) -> CurrentUserResponse:
    try:
        email = accept_invitation(db, payload)
        raw_token = login(db, email, payload.password, request.headers.get("user-agent"), remember=False)
    except (TeamError, AuthError) as error:
        _raise(error)
    set_session_cookie(response, raw_token, remember=False)
    return current_user(db, raw_token)
