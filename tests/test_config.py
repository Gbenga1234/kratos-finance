import pytest
from pydantic import ValidationError

from app.config import Settings


def test_production_requires_external_identity_and_tls_dependencies() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production")


def test_production_accepts_explicit_secure_dependencies() -> None:
    settings = Settings(
        app_env="production",
        database_url=(
            "postgresql+psycopg://service:s3cure-password@db.example.test/finance"
            "?sslmode=verify-full"
        ),
        celery_broker_url="rediss://:secure-password@redis.example.test:6379/0",
        celery_result_backend="rediss://:secure-password@redis.example.test:6379/1",
        oidc_issuer="https://identity.example.test/",
        oidc_audience="kratos-api",
        oidc_jwks_url="https://identity.example.test/.well-known/jwks.json",
        trusted_hosts=["api.example.test"],
    )

    assert settings.app_env == "production"
    assert settings.supported_currencies == ["USD", "EUR", "GBP"]


def test_production_rejects_development_hosts_and_redis() -> None:
    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            database_url=(
                "postgresql+psycopg://service:secret@db.example.test/finance"
                "?sslmode=verify-full"
            ),
            celery_broker_url="redis://redis.example.test:6379/0",
            celery_result_backend="redis://redis.example.test:6379/1",
            oidc_issuer="https://identity.example.test/",
            oidc_audience="kratos-api",
            oidc_jwks_url="https://identity.example.test/.well-known/jwks.json",
            trusted_hosts=["*"],
        )
