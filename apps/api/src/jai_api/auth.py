"""Supabase JWT verification.

Supports both signing modes Supabase uses in the wild:

  * HS256  — older projects, verified with the shared `SUPABASE_JWT_SECRET`.
  * ES256 / RS256 — newer projects, asymmetric. The verifier discovers the
    public key set at `{SUPABASE_URL}/auth/v1/.well-known/jwks.json` and
    selects the key whose `kid` matches the token header. JWKS is cached
    (PyJWKClient handles the LRU and refresh on miss).

We pick the path by reading the token's unverified header. If the alg is
asymmetric and we don't have a Supabase URL configured, we 401 instead of
silently falling through to HS256.
"""

from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from jwt import PyJWKClient

from .config import Settings, get_settings


class CurrentUser:
    def __init__(self, user_id: str, email: str | None = None):
        self.user_id = user_id
        self.email = email


# PyJWKClient maintains its own LRU; one client per JWKS URL is fine.
_jwks_clients: dict[str, PyJWKClient] = {}


def _jwks_client_for(supabase_url: str) -> PyJWKClient:
    url = supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
    client = _jwks_clients.get(url)
    if client is None:
        client = PyJWKClient(url, cache_keys=True, lifespan=3600)
        _jwks_clients[url] = client
    return client


def _decode(token: str, settings: Settings | None = None) -> dict:
    s = settings or get_settings()

    # Sniff the algorithm before we choose a verification path. If the header
    # is malformed we still want a clean 401, not a 500.
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token header: {e}") from e

    alg = (header.get("alg") or "").upper()

    # Asymmetric — verify via Supabase JWKS.
    if alg in {"ES256", "RS256", "EdDSA"}:
        if not s.supabase_url:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "asymmetric JWT received but SUPABASE_URL not configured",
            )
        try:
            signing_key = _jwks_client_for(s.supabase_url).get_signing_key_from_jwt(token).key
            return jwt.decode(
                token,
                signing_key,
                algorithms=[alg],
                audience="authenticated",
                # Supabase ES256 tokens use the project URL as issuer.
                # Don't enforce iss strictly; alg+aud+sig+exp is enough.
                options={"verify_iss": False},
            )
        except jwt.PyJWTError as e:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}") from e

    # Symmetric (legacy projects).
    if alg == "HS256":
        if not s.supabase_jwt_secret:
            if s.jai_user_id:
                return {"sub": s.jai_user_id, "email": "dev@jai.local"}
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR, "no JWT secret configured"
            )
        try:
            return jwt.decode(
                token,
                s.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        except jwt.PyJWTError as e:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}") from e

    raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"unsupported JWT alg: {alg or 'unknown'}")


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        # dev fallback
        settings = get_settings()
        if settings.jai_user_id:
            return CurrentUser(user_id=settings.jai_user_id)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    claims = _decode(token)
    return CurrentUser(user_id=claims["sub"], email=claims.get("email"))


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
