from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

TaskStatus = Literal["todo", "in_progress", "done"]
TaskPriority = Literal["low", "normal", "high", "urgent"]
TaskSort = Literal["due_date", "-priority", "-created_at", "-completed_at", "title"]
TaskDue = Literal["overdue", "today", "week", "none"]


class TaskInput(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    status: TaskStatus = "todo"
    priority: TaskPriority = "normal"
    due_date: date | None = None
    assignee_id: UUID | None = None
    project_id: UUID | None = None
    customer_id: UUID | None = None
    order_id: UUID | None = None

    @field_validator("title", mode="before")
    @classmethod
    def clean_title(cls, value: object) -> object:
        return " ".join(value.split()) if isinstance(value, str) else value

    @field_validator("description", mode="before")
    @classmethod
    def clean_description(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value


class TaskStatusInput(BaseModel):
    status: TaskStatus


class TaskItem(BaseModel):
    id: UUID
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    due_date: date | None
    overdue: bool
    assignee_id: UUID | None
    assignee_name: str | None
    project_id: UUID | None
    project_name: str | None
    customer_id: UUID | None = None
    customer_name: str | None = None
    order_id: UUID | None = None
    order_code: str | None = None
    depends_on: list["TaskRef"] = Field(default_factory=list)
    blocked: bool = False
    automatic: bool = False
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TaskPage(BaseModel):
    items: list[TaskItem]
    total: int
    page: int
    page_size: int
    today: date


class TaskSummary(BaseModel):
    todo: int
    in_progress: int
    done: int
    overdue: int
    due_today: int
    today: date


class Assignee(BaseModel):
    id: UUID
    name: str
    me: bool


class TaskRef(BaseModel):
    id: UUID
    title: str
    status: TaskStatus


class DependencyInput(BaseModel):
    depends_on: list[UUID] = Field(default_factory=list, max_length=20)


class TemplateItem(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    priority: TaskPriority = "normal"
    offset_days: int | None = Field(default=None, ge=0, le=365)
    depends_on: list[int] = Field(default_factory=list, max_length=20)

    @field_validator("title", mode="before")
    @classmethod
    def clean_title(cls, value: object) -> object:
        return " ".join(value.split()) if isinstance(value, str) else value


class TemplateInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    items: list[TemplateItem] = Field(min_length=1, max_length=30)

    @field_validator("items")
    @classmethod
    def earlier_only(cls, items: list[TemplateItem]) -> list[TemplateItem]:
        for index, item in enumerate(items):
            if any(parent < 0 or parent >= index for parent in item.depends_on):
                raise ValueError(f"{index + 1}. adım yalnızca kendinden önceki adımlara bağlanabilir.")
        return items


class TemplateOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    items: list[TemplateItem]
    created_at: datetime
    updated_at: datetime


class TemplateApply(BaseModel):
    start_date: date | None = None
    assignee_id: UUID | None = None
    customer_id: UUID | None = None
    order_id: UUID | None = None
    project_id: UUID | None = None
    once_per_record: bool = True


class TemplateApplied(BaseModel):
    created: list[TaskItem]


class AssigneeLoad(BaseModel):
    assignee_id: UUID | None
    name: str
    open: int
    overdue: int
    this_week: int


class TodayView(BaseModel):
    today: date
    overdue: list[TaskItem]
    due_today: list[TaskItem]
    in_progress: list[TaskItem]
    upcoming: list[TaskItem]
    waiting: list[TaskItem]
    unblocked: list[TaskItem]
    load: list[AssigneeLoad]


TaskItem.model_rebuild()
