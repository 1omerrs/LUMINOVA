import logging

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

logger = logging.getLogger(__name__)
GENERIC_ERROR_DETAIL = "Beklenmeyen bir hata oluştu."


def _validation_message(error: dict[str, object]) -> str:
    location = error.get("loc", ())
    loc = location if isinstance(location, (tuple, list)) else ()
    error_type = error.get("type")
    if "password" in loc and error_type == "string_too_short":
        return "Şifre en az 10 karakter olmalı."
    if "email" in loc:
        return "Geçerli bir e-posta adresi girin."
    if error_type == "value_error":
        context = error.get("ctx")
        reason = context.get("error") if isinstance(context, dict) else None
        if reason is not None:
            return str(reason)
    if error_type == "string_too_short":
        return "Bu alan çok kısa."
    if error_type == "string_too_long":
        return "Bu alan çok uzun."
    if error_type == "missing":
        return "Bu alan gerekli."
    return "Bu alanı kontrol edin."


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    del request
    details = [
        {"loc": [str(part) for part in error.get("loc", ())], "msg": _validation_message(error)}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": details})


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, StarletteHTTPException):
        detail = exc.detail if isinstance(exc.detail, (str, list, dict)) else "İstek tamamlanamadı."
        return JSONResponse(status_code=exc.status_code, content={"detail": detail}, headers=exc.headers)
    logger.exception("Unhandled application error path=%s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": GENERIC_ERROR_DETAIL})
