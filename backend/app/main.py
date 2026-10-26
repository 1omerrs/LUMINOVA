import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import unhandled_exception_handler, validation_exception_handler
from app.api.middleware import RequestIdMiddleware
from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    docs_enabled = settings.app_env != "production"

    app = FastAPI(
        title="LUMINOVA API",
        version=settings.app_version,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID", "X-CSRF-Token"],
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        payload = {
            "service": "luminova-api",
            "health": f"{settings.api_prefix}/health",
        }
        if docs_enabled:
            payload["docs"] = "/docs"
        return payload

    logger.info(
        "LUMINOVA API initialized env=%s version=%s",
        settings.app_env,
        settings.app_version,
    )
    return app


app = create_app()
