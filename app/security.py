from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWTError

from app.config import get_settings

bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=8)
def get_jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_jwk_set=True, lifespan=300, timeout=5)


def authenticated_subject(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> str:
    settings = get_settings()
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not all((settings.oidc_issuer, settings.oidc_audience, settings.oidc_jwks_url)):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Identity provider is not configured",
        )

    try:
        signing_key = get_jwks_client(settings.oidc_jwks_url).get_signing_key_from_jwt(
            credentials.credentials
        )
        claims = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            leeway=30,
        )
    except PyJWKClientConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Identity provider is temporarily unavailable",
        ) from exc
    except (PyJWTError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    subject = claims.get("sub")
    if (
        not isinstance(subject, str)
        or not subject
        or len(subject) > 255
        or subject == "legacy-unowned"
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token subject",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return subject
