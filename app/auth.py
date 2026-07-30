"""Cookie gate for /settings and its API.

Deliberately simple: one shared password (ADMIN_PASSWORD), no accounts. The
cookie holds an HMAC of a fixed message keyed by the password, not the
password itself, so it's verifiable statelessly (no session store needed
across serverless invocations) without putting the plaintext password in a
cookie. Fails closed: if ADMIN_PASSWORD isn't set, protected routes refuse
access rather than silently allowing it.
"""

import hashlib
import hmac

from fastapi import HTTPException, Request

from app.config import ADMIN_PASSWORD

COOKIE_NAME = "kh_auth"
_TOKEN_MESSAGE = b"kom-hunter-authenticated"


class AuthNotConfigured(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(ADMIN_PASSWORD)


def _expected_token() -> str:
    if not ADMIN_PASSWORD:
        raise AuthNotConfigured
    return hmac.new(ADMIN_PASSWORD.encode(), _TOKEN_MESSAGE, hashlib.sha256).hexdigest()


def check_password(password: str) -> bool:
    if not ADMIN_PASSWORD:
        raise AuthNotConfigured
    return hmac.compare_digest(password, ADMIN_PASSWORD)


def make_cookie_value() -> str:
    return _expected_token()


def is_authenticated(request: Request) -> bool:
    try:
        expected = _expected_token()
    except AuthNotConfigured:
        return False
    cookie = request.cookies.get(COOKIE_NAME, "")
    return bool(cookie) and hmac.compare_digest(cookie, expected)


def require_auth(request: Request) -> None:
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Not authenticated")
