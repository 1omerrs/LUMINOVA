from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import current_member, require_csrf
from app.core.database import get_db
from app.schemas.modules import ModuleItem, ModuleListResponse, ModuleSelectionRequest
from app.services.auth import Member
from app.services.modules import ModuleError, complete_setup, list_modules, module_access, update_selection

router = APIRouter()


def _raise_module(error: ModuleError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.detail)


@router.get("/modules", response_model=ModuleListResponse)
def read_modules(db: Session = Depends(get_db), member: Member = Depends(current_member)) -> ModuleListResponse:
    return list_modules(db, member)


@router.put("/modules", response_model=ModuleListResponse)
def change_modules(
    payload: ModuleSelectionRequest,
    db: Session = Depends(get_db),
    member: Member = Depends(current_member),
    _: None = Depends(require_csrf),
) -> ModuleListResponse:
    try:
        return update_selection(db, member, payload.modules)
    except ModuleError as error:
        _raise_module(error)


@router.get("/modules/{module_key}", response_model=ModuleItem)
def read_module(module_key: str, db: Session = Depends(get_db), member: Member = Depends(current_member)) -> ModuleItem:
    try:
        return module_access(db, member, module_key)
    except ModuleError as error:
        _raise_module(error)


@router.post("/workspace/setup", response_model=ModuleListResponse)
def setup_workspace(
    payload: ModuleSelectionRequest,
    db: Session = Depends(get_db),
    member: Member = Depends(current_member),
    _: None = Depends(require_csrf),
) -> ModuleListResponse:
    try:
        return complete_setup(db, member, payload.modules)
    except ModuleError as error:
        _raise_module(error)
