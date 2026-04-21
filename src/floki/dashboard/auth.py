from __future__ import annotations

import secrets
import time

from fastapi import HTTPException, Request, status

from floki.config import settings
from floki.security import verify_pin

SESSION_COOKIE = "floki_session"
SESSION_TTL = 60 * 30  # 30 min, matches Telegram unlock window

_SESSIONS: dict[str, float] = {}


def create_session() -> str:
    token = secrets.token_urlsafe(32)
    _SESSIONS[token] = time.time() + SESSION_TTL
    return token


def is_valid_session(token: str | None) -> bool:
    if not token:
        return False
    exp = _SESSIONS.get(token)
    if not exp:
        return False
    if exp < time.time():
        _SESSIONS.pop(token, None)
        return False
    return True


def drop_session(token: str | None) -> None:
    if token:
        _SESSIONS.pop(token, None)


def verify_pin_attempt(pin: str) -> bool:
    return verify_pin(pin, settings().pin_hash)


def require_session(request: Request) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if not is_valid_session(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="PIN required")


def require_session_or_ws_secret(request: Request, key: str | None) -> None:
    """Accept either a valid PIN session cookie or the PIPECAT_WS_SECRET query param.
    Used by the Pipecat WebSocket so the voice daemon can connect without PIN UX.
    """
    token = request.cookies.get(SESSION_COOKIE)
    if is_valid_session(token):
        return
    expected = settings().pipecat_ws_secret
    if expected and key and secrets.compare_digest(expected, key):
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="auth required")
