import os
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_LOCAL_DATABASE_URL = "postgresql+psycopg://luminova:luminova@127.0.0.1:5433/luminova"
PSYCOPG_SCHEME = "postgresql+psycopg://"
LOCAL_WEBHOOK_KEY = "local-only-webhook-key-change-me-in-production"


def package_version() -> str:
    try:
        return version("luminova-api")
    except PackageNotFoundError:
        return "0.1.0"


class Settings(BaseSettings):
    app_env: Literal["local", "test", "production"] = "local"
    app_name: str = "LUMINOVA"
    app_version: str = Field(default_factory=package_version)
    api_prefix: str = "/api/v1"
    database_url: str = ""
    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"
    webhook_secret_key: str = ""
    mail_webhook_url: str = ""
    mail_webhook_secret: str = ""
    public_app_url: str = "http://127.0.0.1:5173"

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: object,
        env_settings: object,
        dotenv_settings: object,
        file_secret_settings: object,
    ) -> tuple[object, ...]:
        if os.getenv("APP_ENV") == "production":
            return (init_settings, env_settings, file_secret_settings)
        return (init_settings, env_settings, dotenv_settings, file_secret_settings)

    @model_validator(mode="before")
    @classmethod
    def apply_local_database_default(cls, data: object) -> object:
        if isinstance(data, dict) and not data.get("database_url") and data.get("app_env", "local") != "production":
            data["database_url"] = DEFAULT_LOCAL_DATABASE_URL
        return data

    @model_validator(mode="after")
    def resolve_runtime_safety(self) -> "Settings":
        if not self.database_url:
            raise ValueError("DATABASE_URL is required when APP_ENV=production")

        if not self.database_url.startswith(PSYCOPG_SCHEME):
            raise ValueError("DATABASE_URL must use the postgresql+psycopg driver")

        if self.app_env == "production" and any(
            "localhost" in origin or "127.0.0.1" in origin for origin in self.cors_origin_list
        ):
            raise ValueError("CORS_ORIGINS must not use localhost when APP_ENV=production")

        if not self.webhook_secret_key:
            if self.app_env == "production":
                raise ValueError("WEBHOOK_SECRET_KEY is required when APP_ENV=production")
            self.webhook_secret_key = LOCAL_WEBHOOK_KEY
        elif self.app_env == "production" and len(self.webhook_secret_key) < 32:
            raise ValueError("WEBHOOK_SECRET_KEY must be at least 32 characters")

        self.public_app_url = self.public_app_url.rstrip("/")
        if self.mail_webhook_url:
            if not self.mail_webhook_secret:
                raise ValueError("MAIL_WEBHOOK_SECRET is required when MAIL_WEBHOOK_URL is set")
            if self.app_env == "production":
                if not self.mail_webhook_url.startswith("https://"):
                    raise ValueError("MAIL_WEBHOOK_URL must use https when APP_ENV=production")
                if len(self.mail_webhook_secret) < 32:
                    raise ValueError("MAIL_WEBHOOK_SECRET must be at least 32 characters")
                if not self.public_app_url.startswith("https://"):
                    raise ValueError("PUBLIC_APP_URL must use https when APP_ENV=production")

        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
