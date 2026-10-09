from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.security import authenticated_subject


@pytest.fixture
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def test_oidc_token_requires_valid_issuer_audience_and_signature(
    monkeypatch: pytest.MonkeyPatch,
    signing_key,
) -> None:
    settings = SimpleNamespace(
        oidc_issuer="https://identity.example.test/",
        oidc_audience="kratos-api",
        oidc_jwks_url="https://identity.example.test/.well-known/jwks.json",
    )
    monkeypatch.setattr("app.security.get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.security.get_jwks_client",
        lambda _: SimpleNamespace(
            get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=signing_key.public_key())
        ),
    )
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "iss": settings.oidc_issuer,
            "aud": settings.oidc_audience,
            "sub": "customer-123",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        signing_key,
        algorithm="RS256",
    )

    subject = authenticated_subject(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    )

    assert subject == "customer-123"


def test_oidc_rejects_wrong_audience(
    monkeypatch: pytest.MonkeyPatch,
    signing_key,
) -> None:
    settings = SimpleNamespace(
        oidc_issuer="https://identity.example.test/",
        oidc_audience="kratos-api",
        oidc_jwks_url="https://identity.example.test/.well-known/jwks.json",
    )
    monkeypatch.setattr("app.security.get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.security.get_jwks_client",
        lambda _: SimpleNamespace(
            get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=signing_key.public_key())
        ),
    )
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "iss": settings.oidc_issuer,
            "aud": "another-service",
            "sub": "customer-123",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        signing_key,
        algorithm="RS256",
    )

    with pytest.raises(HTTPException) as error:
        authenticated_subject(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        )

    assert error.value.status_code == 401


def test_oidc_rejects_token_signed_by_unknown_key(
    monkeypatch: pytest.MonkeyPatch,
    signing_key,
) -> None:
    untrusted_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = SimpleNamespace(
        oidc_issuer="https://identity.example.test/",
        oidc_audience="kratos-api",
        oidc_jwks_url="https://identity.example.test/.well-known/jwks.json",
    )
    monkeypatch.setattr("app.security.get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.security.get_jwks_client",
        lambda _: SimpleNamespace(
            get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=signing_key.public_key())
        ),
    )
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "iss": settings.oidc_issuer,
            "aud": settings.oidc_audience,
            "sub": "customer-123",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        untrusted_key,
        algorithm="RS256",
    )

    with pytest.raises(HTTPException) as error:
        authenticated_subject(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        )

    assert error.value.status_code == 401
