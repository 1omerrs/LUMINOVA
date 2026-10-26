from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_module
from app.core.database import get_db
from app.modules.reporting.schemas import ReportOverview
from app.modules.reporting.service import overview
from app.services.auth import Member

router = APIRouter(prefix="/reports")
reporting_member = require_module("reporting")
PERIODS = (3, 6, 12)


@router.get("/overview", response_model=ReportOverview)
def read_overview(
    months: int = Query(default=6),
    db: Session = Depends(get_db),
    member: Member = Depends(reporting_member),
) -> ReportOverview:
    if months not in PERIODS:
        raise HTTPException(status_code=422, detail="Dönem 3, 6 veya 12 ay olabilir.")
    return overview(db, member, months)
