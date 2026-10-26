from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.mail import MailCallbackResult
from app.services import mail

router = APIRouter(prefix="/mail")
MAX_BODY = 16 * 1024


@router.post("/callback", response_model=MailCallbackResult)
async def receive_result(request: Request, db: Session = Depends(get_db)) -> MailCallbackResult:
    body = await request.body()
    if len(body) > MAX_BODY:
        raise HTTPException(status_code=413, detail="İstek gövdesi 16 KB sınırını aşıyor.")
    headers = {key.lower(): value for key, value in request.headers.items()}
    try:
        message = mail.handle_callback(db, headers, body)
    except mail.MailError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None
    return MailCallbackResult(ok=True, id=message.id, status=message.status)  # type: ignore[arg-type]
