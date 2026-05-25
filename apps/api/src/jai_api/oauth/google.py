"""Google OAuth helper. One client app, multiple services with different scopes.

Token blob is stored as a single encrypted credential keyed by service:
  GMAIL_OAUTH_JSON     -> json.dumps({access_token, refresh_token, token_uri, client_id, client_secret, scopes, expiry})
  CALENDAR_OAUTH_JSON
  DRIVE_OAUTH_JSON

Skills reconstruct credentials from this blob via
`google.oauth2.credentials.Credentials.from_authorized_user_info`.
"""

from __future__ import annotations

import json
from typing import Literal

from google_auth_oauthlib.flow import Flow
from itsdangerous import BadSignature, URLSafeSerializer

from ..config import get_settings

Service = Literal["gmail", "calendar", "drive"]

_SCOPES: dict[Service, list[str]] = {
    "gmail": [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/userinfo.email",
    ],
    "calendar": [
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/userinfo.email",
    ],
    "drive": [
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/userinfo.email",
    ],
}


def _serializer() -> URLSafeSerializer:
    s = get_settings()
    return URLSafeSerializer(s.jai_credentials_key or "dev-only-state-secret", salt="google-oauth")


def _flow(service: Service) -> Flow:
    s = get_settings()
    if not (s.google_oauth_client_id and s.google_oauth_client_secret):
        raise RuntimeError("GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET not set")
    return Flow.from_client_config(
        {
            "web": {
                "client_id": s.google_oauth_client_id,
                "client_secret": s.google_oauth_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [s.google_oauth_redirect_uri],
            }
        },
        scopes=_SCOPES[service],
        redirect_uri=s.google_oauth_redirect_uri,
    )


def auth_url(*, user_id: str, service: Service, return_to: str) -> str:
    flow = _flow(service)
    state = _serializer().dumps({"u": user_id, "s": service, "r": return_to})
    url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",   # always issue refresh_token
        include_granted_scopes="true",
        state=state,
    )
    return url


def decode_state(state: str) -> dict:
    try:
        return _serializer().loads(state)
    except BadSignature as e:
        raise ValueError("invalid OAuth state") from e


def exchange_code(*, service: Service, code: str) -> dict:
    flow = _flow(service)
    flow.fetch_token(code=code)
    c = flow.credentials
    return {
        "access_token": c.token,
        "refresh_token": c.refresh_token,
        "token_uri": c.token_uri,
        "client_id": c.client_id,
        "client_secret": c.client_secret,
        "scopes": list(c.scopes or []),
        "expiry": c.expiry.isoformat() if c.expiry else None,
    }


def credential_key_for(service: Service) -> str:
    return f"{service.upper()}_OAUTH_JSON"
