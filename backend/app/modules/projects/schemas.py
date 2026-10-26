from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, ValidationInfo, field_validator

ProjectStatus = Literal["planned", "active", "on_hold", "completed"]
ProjectSort = Literal["due_date", "-created_at", "name"]


class ProjectInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    status: ProjectStatus = "planned"
    customer_id: UUID | None = None
    quote_id: UUID | None = None
    order_id: UUID | None = None
    start_date: date | None = None
    due_date: date | None = None
    template_id: UUID | None = None
    working_days_only: bool = False

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value: object) -> object:
        return " ".join(value.split()) if isinstance(value, str) else value

    @field_validator("description", mode="before")
    @classmethod
    def clean_description(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("due_date")
    @classmethod
    def due_after_start(cls, value: date | None, info: ValidationInfo) -> date | None:
        start = info.data.get("start_date")
        if value is not None and start is not None and value < start:
            raise ValueError("Teslim tarihi başlangıç tarihinden önce olamaz.")
        return value


class ProjectItem(BaseModel):
    id: UUID
    name: str
    description: str | None
    status: ProjectStatus
    customer_id: UUID | None
    customer_name: str | None
    quote_id: UUID | None = None
    quote_code: str | None = None
    order_id: UUID | None = None
    order_code: str | None = None
    start_date: date | None
    due_date: date | None
    working_days_only: bool = False
    overdue: bool
    completed_at: datetime | None
    task_total: int
    task_done: int
    task_overdue: int
    progress: int
    milestone_total: int = 0
    milestone_done: int = 0
    next_milestone: str | None = None
    next_milestone_due: date | None = None
    created_at: datetime
    updated_at: datetime


class MilestoneInput(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    due_date: date | None = None
    done: bool = False

    @field_validator("title", mode="before")
    @classmethod
    def clean_title(cls, value: object) -> object:
        return " ".join(value.split()) if isinstance(value, str) else value


class MilestoneItem(BaseModel):
    id: UUID
    title: str
    due_date: date | None
    done: bool
    overdue: bool
    completed_at: datetime | None
    position: int


class MilestoneMove(BaseModel):
    direction: Literal["up", "down"]


class ProjectPage(BaseModel):
    items: list[ProjectItem]
    total: int
    page: int
    page_size: int
    today: date


class ProjectSummary(BaseModel):
    planned: int
    active: int
    on_hold: int
    completed: int
    overdue: int


class ProjectTemplateItem(BaseModel):
    stage: str = Field(min_length=2, max_length=160)
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    duration_days: int = Field(default=1, ge=1, le=365)
    depends_on: list[int] = Field(default_factory=list, max_length=20)

    @field_validator("stage", "title", mode="before")
    @classmethod
    def clean_text(cls, value: object) -> object:
        return " ".join(value.split()) if isinstance(value, str) else value


class ProjectTemplateInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    items: list[ProjectTemplateItem] = Field(min_length=1, max_length=60)

    @field_validator("items")
    @classmethod
    def earlier_only(cls, items: list[ProjectTemplateItem]) -> list[ProjectTemplateItem]:
        for index, item in enumerate(items):
            if any(parent < 0 or parent >= index for parent in item.depends_on):
                raise ValueError(f"{index + 1}. görev yalnızca kendinden önceki görevlere bağlanabilir.")
        return items


class ProjectTemplateOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    items: list[ProjectTemplateItem]
    stages: list[str]
    total_days: int
    created_at: datetime
    updated_at: datetime


class PlanTask(BaseModel):
    id: UUID
    title: str
    status: Literal["todo", "in_progress", "done"]
    priority: Literal["low", "normal", "high", "urgent"]
    start_date: date | None
    due_date: date | None
    duration_days: int | None
    milestone_id: UUID | None
    depends_on: list[UUID]
    assignee_name: str | None
    blocked: bool
    overdue: bool
    critical: bool


RiskKind = Literal["late_finish", "behind", "overdue_task", "bottleneck", "unassigned", "late_milestone", "no_plan"]


class PlanRisk(BaseModel):
    kind: RiskKind
    severity: Literal["high", "medium", "low"]
    title: str
    detail: str
    task_id: UUID | None = None


class ScheduleChange(BaseModel):
    task_id: UUID
    title: str
    old_start: date | None
    old_due: date | None
    new_start: date
    new_due: date


class ProjectPlan(BaseModel):
    today: date
    tasks: list[PlanTask]
    milestones: list[MilestoneItem]
    actual_progress: int
    expected_progress: int | None
    projected_finish: date | None
    delay_days: int
    risks: list[PlanRisk]
    pending_changes: int


class RescheduleInput(BaseModel):
    apply: bool = False


class RescheduleResult(BaseModel):
    changes: list[ScheduleChange]
    projected_finish: date | None
    delay_days: int
    applied: bool
