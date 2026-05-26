"""Google OAuth helper. One client app, multiple services with different scopes.

Token blob is stored as a single encrypted credential keyed by service:
  GMAIL_OAUTH_JSON     -> json.dumps({access_token, refresh_token, token_uri, client_id, client_secret, scopes, expiry})
  CALENDAR_OAUTH_JSON
  DRIVE_OAUTH_JSON

Skills reconstruct credentials from this blob via
`google.oauth2.credentials.Credentials.from_authorized_user_info`.
"""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlencode

import requests
from itsdangerous import BadSignature, URLSafeSerializer

from ..config import get_settings

Service = Literal["gmail", "calendar", "drive"]

_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
_TOKEN_URI = "https://oauth2.googleapis.com/token"
_USERINFO_URI = "https://openidconnect.googleapis.com/v1/userinfo"

_SCOPES: dict[Service, list[str]] = {
    "gmail": [
        "openid",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/userinfo.email",
    ],
    "calendar": [
        "openid",
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/userinfo.email",
    ],
    "drive": [
        "openid",
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/userinfo.email",
    ],
}


def fetch_userinfo(access_token: str) -> dict:
    """Return Google userinfo (email, name, picture, sub) for an access token."""
    resp = requests.get(
        _USERINFO_URI,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"google userinfo failed ({resp.status_code}): {resp.text}")
    return resp.json()


def _serializer() -> URLSafeSerializer:
    s = get_settings()
    return URLSafeSerializer(s.jai_credentials_key or "dev-only-state-secret", salt="google-oauth")


def _require_client() -> tuple[str, str, str]:
    s = get_settings()
    if not (s.google_oauth_client_id and s.google_oauth_client_secret):
        raise RuntimeError("GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET not set")
    if not s.google_oauth_redirect_uri:
        raise RuntimeError("GOOGLE_OAUTH_REDIRECT_URI not set")
    return s.google_oauth_client_id, s.google_oauth_client_secret, s.google_oauth_redirect_uri


def auth_url(*, user_id: str, service: Service, return_to: str) -> str:
    """Build a Google OAuth authorization URL.

    Uses the plain confidential web-client flow (no PKCE) — `client_secret`
    on the token exchange is enough to identify us. We previously relied on
    `google_auth_oauthlib.Flow` which auto-injects PKCE and then 500s on the
    callback because the verifier isn't persisted across the redirect.
    """
    client_id, _client_secret, redirect_uri = _require_client()
    state = _serializer().dumps({"u": user_id, "s": service, "r": return_to})
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(_SCOPES[service]),
        "access_type": "offline",
        # `select_account` makes Google show the account picker every time,
        # so adding a 2nd / 3rd Gmail account works even when the browser
        # is already signed in to a Google account. `consent` forces issuing
        # a refresh_token.
        "prompt": "select_account consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{_AUTH_URI}?{urlencode(params)}"


def decode_state(state: str) -> dict:
    try:
        return _serializer().loads(state)
    except BadSignature as e:
        raise ValueError("invalid OAuth state") from e


def exchange_code(*, service: Service, code: str) -> dict:
    """Exchange an authorization code for tokens via direct POST to Google.

    Sidesteps `google_auth_oauthlib`'s stateful PKCE flow which fails in
    this stateless request/redirect model.
    """
    client_id, client_secret, redirect_uri = _require_client()
    resp = requests.post(
        _TOKEN_URI,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        },
        timeout=15,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"google token exchange failed ({resp.status_code}): {resp.text}")
    data = resp.json()
    scopes = (data.get("scope") or "").split() or list(_SCOPES[service])
    expires_in = data.get("expires_in")
    expiry = None
    if expires_in:
        from datetime import datetime, timedelta, timezone
        expiry = (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))).isoformat()
    return {
        "access_token": data.get("access_token"),
        "refresh_token": data.get("refresh_token"),
        "token_uri": _TOKEN_URI,
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": scopes,
        "expiry": expiry,
    }


def credential_key_for(service: Service) -> str:
    return f"{service.upper()}_OAUTH_JSON"
