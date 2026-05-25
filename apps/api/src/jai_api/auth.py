"""Supabase JWT verification."""

from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status

from .config import get_settings


class CurrentUser:
    def __init__(self, user_id: str, email: str | None = None):
        self.user_id = user_id
        self.email = email


def _decode(token: str) -> dict:
    settings = get_settings()
    if not settings.supabase_jwt_secret:
        # Dev-only escape hatch: trust a fixed user id.
        if settings.jai_user_id:
            return {"sub": settings.jai_user_id, "email": "dev@jai.local"}
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "no JWT secret configured")
    try:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}") from e


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
