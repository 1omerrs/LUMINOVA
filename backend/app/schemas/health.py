from typing import Literal

from pydantic import BaseModel


class HealthChecks(BaseModel):
    database: Literal["ok", "unavailable"]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    environment: str
    version: str
    checks: HealthChecks
