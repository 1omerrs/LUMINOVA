import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.schemas.health import HealthChecks, HealthResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse)
def read_health(db: Session = Depends(get_db)) -> JSONResponse:
    settings = get_settings()
    database_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Database health check failed")
        database_status = "unavailable"

    payload = HealthResponse(
        status="ok" if database_status == "ok" else "degraded",
        service="luminova-api",
        environment=settings.app_env,
        version=settings.app_version,
        checks=HealthChecks(database=database_status),
    )
    status_code = 200 if payload.status == "ok" else 503
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(),
        headers={"Cache-Control": "no-store"},
    )
