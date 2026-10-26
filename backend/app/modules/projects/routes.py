from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import require_csrf, require_module
from app.core.database import get_db
from app.modules.projects.schemas import (
    MilestoneInput,
    MilestoneItem,
    MilestoneMove,
    ProjectInput,
    ProjectItem,
    ProjectPage,
    ProjectPlan,
    ProjectSort,
    ProjectStatus,
    ProjectSummary,
    ProjectTemplateInput,
    ProjectTemplateOut,
    RescheduleInput,
    RescheduleResult,
)
from app.modules.projects import planning
from app.modules.projects.service import (
    ProjectError,
    add_milestone,
    create_project,
    delete_milestone,
    delete_project,
    get_plan,
    get_project,
    reschedule_project,
    list_milestones,
    list_projects,
    move_milestone,
    project_summary,
    update_milestone,
    update_project,
)
from app.services.auth import Member

router = APIRouter(prefix="/projects")
projects_member = require_module("projects")


def _raise(error: ProjectError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.detail)


@router.get("/summary", response_model=ProjectSummary)
def read_summary(db: Session = Depends(get_db), member: Member = Depends(projects_member)) -> ProjectSummary:
    return project_summary(db, member)


@router.get("/templates", response_model=list[ProjectTemplateOut])
def read_templates(db: Session = Depends(get_db), member: Member = Depends(projects_member)) -> list[ProjectTemplateOut]:
    return planning.list_templates(db, member)


@router.post("/templates", response_model=ProjectTemplateOut, status_code=201)
def add_template(
    payload: ProjectTemplateInput,
    db: Session = Depends(get_db),
    member: Member = Depends(projects_member),
    _: None = Depends(require_csrf),
) -> ProjectTemplateOut:
    return planning.save_template(db, member, payload)


@router.put("/templates/{template_id}", response_model=ProjectTemplateOut)
def change_template(
    template_id: UUID,
    payload: ProjectTemplateInput,
    db: Session = Depends(get_db),
    member: Member = Depends(projects_member),
    _: None = Depends(require_csrf),
) -> ProjectTemplateOut:
    try:
        return planning.save_template(db, member, payload, template_id)
    except ProjectError as error:
        _raise(error)


@router.delete("/templates/{template_id}", status_code=204)
def remove_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    member: Member = Depends(projects_member),
    _: None = Depends(require_csrf),
) -> Response:
    try:
        planning.delete_template(db, member, template_id)
    except ProjectError as error:
        _raise(error)
    return Response(status_code=204)


@router.get("", response_model=ProjectPage)
def read_projects(
    q: str | None = Query(default=None, max_length=120),
    status: ProjectStatus | None = None,
    sort: ProjectSort = "due_date",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
    db: Session = Depends(get_db),
    member: Member = Depends(projects_member),
) -> ProjectPage:
    return list_projects(db, member, query=q, status=status, sort=sort, page=page, page_size=page_size)


@router.post("", response_model=ProjectItem, status_code=201)
def add_project(
    payload: ProjectInput,
    db: Session = Depends(get_db),
    member: Member = Depends(projects_member),
    _: None = Depends(require_csrf),
) -> ProjectItem:
    try:
        return create_project(db, member, payload)
    except ProjectError as error:
        _raise(error)


@router.get("/{project_id}", response_model=ProjectItem)
def read_project(project_id: UUID, db: Session = Depends(get_db), member: Member = Depends(projects_member)) -> ProjectItem:
    try:
        return get_project(db, member, project_id)
    except ProjectError as error:
        _raise(error)


@router.put("/{project_id}", response_model=ProjectItem)
def change_project(
    project_id: UUID,
    payload: ProjectInput,
    db: Session = Depends(get_db),
    member: Member = Depends(projects_member),
    _: None = Depends(require_csrf),
) -> ProjectItem:
    try:
        return update_project(db, member, project_id, payload)
    except ProjectError as error:
        _raise(error)


@router.get("/{project_id}/plan", response_model=ProjectPlan)
def read_plan(project_id: UUID, db: Session = Depends(get_db), member: Member = Depends(projects_member)) -> ProjectPlan:
    try:
        return get_plan(db, member, project_id)
    except ProjectError as error:
        _raise(error)


@router.post("/{project_id}/reschedule", response_model=RescheduleResult)
def reschedule(
    project_id: UUID,
    payload: RescheduleInput,
    db: Session = Depends(get_db),
    member: Member = Depends(projects_member),
    _: None = Depends(require_csrf),
) -> RescheduleResult:
    try:
        return reschedule_project(db, member, project_id, apply=payload.apply)
    except ProjectError as error:
        _raise(error)


@router.get("/{project_id}/milestones", response_model=list[MilestoneItem])
def read_milestones(project_id: UUID, db: Session = Depends(get_db), member: Member = Depends(projects_member)) -> list[MilestoneItem]:
    try:
        return list_milestones(db, member, project_id)
    except ProjectError as error:
        _raise(error)


@router.post("/{project_id}/milestones", response_model=list[MilestoneItem], status_code=201)
def add_project_milestone(
    project_id: UUID,
    payload: MilestoneInput,
    db: Session = Depends(get_db),
    member: Member = Depends(projects_member),
    _: None = Depends(require_csrf),
) -> list[MilestoneItem]:
    try:
        return add_milestone(db, member, project_id, payload)
    except ProjectError as error:
        _raise(error)


@router.put("/{project_id}/milestones/{milestone_id}", response_model=list[MilestoneItem])
def change_milestone(
    project_id: UUID,
    milestone_id: UUID,
    payload: MilestoneInput,
    db: Session = Depends(get_db),
    member: Member = Depends(projects_member),
    _: None = Depends(require_csrf),
) -> list[MilestoneItem]:
    try:
        return update_milestone(db, member, project_id, milestone_id, payload)
    except ProjectError as error:
        _raise(error)


@router.post("/{project_id}/milestones/{milestone_id}/move", response_model=list[MilestoneItem])
def reorder_milestone(
    project_id: UUID,
    milestone_id: UUID,
    payload: MilestoneMove,
    db: Session = Depends(get_db),
    member: Member = Depends(projects_member),
    _: None = Depends(require_csrf),
) -> list[MilestoneItem]:
    try:
        return move_milestone(db, member, project_id, milestone_id, payload.direction)
    except ProjectError as error:
        _raise(error)


@router.delete("/{project_id}/milestones/{milestone_id}", response_model=list[MilestoneItem])
def remove_milestone(
    project_id: UUID,
    milestone_id: UUID,
    db: Session = Depends(get_db),
    member: Member = Depends(projects_member),
    _: None = Depends(require_csrf),
) -> list[MilestoneItem]:
    try:
        return delete_milestone(db, member, project_id, milestone_id)
    except ProjectError as error:
        _raise(error)


@router.delete("/{project_id}", status_code=204)
def remove_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    member: Member = Depends(projects_member),
    _: None = Depends(require_csrf),
) -> Response:
    try:
        delete_project(db, member, project_id)
    except ProjectError as error:
        _raise(error)
    return Response(status_code=204)
