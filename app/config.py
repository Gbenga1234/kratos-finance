from functools import lru_cache
import re
from urllib.parse import urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    app_name: str = "Kratos Finance"
    app_env: str = "development"
    database_url: str = "sqlite:///./kratos_finance.db"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    log_level: str = "INFO"
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    trusted_hosts: list[str] = ["localhost", "127.0.0.1", "testserver"]
    max_transfer_amount: int = 100_000_00
    supported_currencies: list[str] = ["USD", "EUR", "GBP"]

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        self.app_env = self.app_env.lower()
        self.supported_currencies = [
            currency.upper() for currency in self.supported_currencies
        ]
        if self.app_env not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production")
        if self.app_env.lower() == "production":
            database = make_url(self.database_url)
            if (
                database.drivername != "postgresql+psycopg"
                or not database.host
                or database.host in {"localhost", "127.0.0.1"}
                or not database.username
                or not database.password
                or database.password == "finance"
                or database.query.get("sslmode") not in {"verify-ca", "verify-full"}
            ):
                raise ValueError(
                    "Production requires remote PostgreSQL credentials and sslmode=verify-full"
                )
            if not all((self.oidc_issuer, self.oidc_audience, self.oidc_jwks_url)):
                raise ValueError("Production requires OIDC issuer, audience, and JWKS URL")
            if not self.oidc_issuer.startswith("https://") or not self.oidc_jwks_url.startswith(
                "https://"
            ):
                raise ValueError("Production OIDC issuer and JWKS URL must use HTTPS")
            if not self.trusted_hosts or "*" in self.trusted_hosts:
                raise ValueError("Production requires explicit trusted hosts")
            for value in (self.celery_broker_url, self.celery_result_backend):
                broker = urlsplit(value)
                if (
                    broker.scheme != "rediss"
                    or not broker.hostname
                    or broker.hostname in {"localhost", "127.0.0.1"}
                    or not broker.password
                ):
                    raise ValueError(
                        "Production Celery endpoints require remote authenticated TLS Redis"
                    )
        if self.max_transfer_amount <= 0:
            raise ValueError("MAX_TRANSFER_AMOUNT must be positive")
        if not self.supported_currencies or any(
            not re.fullmatch(r"[A-Z]{3}", currency)
            for currency in self.supported_currencies
        ):
            raise ValueError("SUPPORTED_CURRENCIES must contain three-letter currency codes")
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
