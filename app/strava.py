import re
import time
import urllib.parse

import requests
from sqlalchemy.orm import Session

from app.db import get_settings

TOKEN_URL = "https://www.strava.com/oauth/token"
AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
API_BASE = "https://www.strava.com/api/v3"

_SEGMENT_URL_RE = re.compile(r"strava\.com/segments/(\d+)")


class StravaError(RuntimeError):
    pass


def parse_segment_id(url_or_id: str) -> int:
    text = url_or_id.strip()
    if text.isdigit():
        return int(text)
    match = _SEGMENT_URL_RE.search(text)
    if not match:
        raise StravaError(
            f"Couldn't find a segment id in '{url_or_id}'. Paste a link like "
            "https://www.strava.com/segments/12345678"
        )
    return int(match.group(1))


def is_connected(db: Session) -> bool:
    s = get_settings(db)
    return bool(s.strava_client_id and s.strava_client_secret and s.strava_refresh_token)


def build_authorize_url(db: Session, redirect_uri: str) -> str:
    s = get_settings(db)
    if not (s.strava_client_id and s.strava_client_secret):
        raise StravaError("Save your Strava Client ID and Secret first.")
    params = {
        "client_id": s.strava_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": "read",
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def exchange_code_for_tokens(db: Session, code: str) -> None:
    s = get_settings(db)
    if not (s.strava_client_id and s.strava_client_secret):
        raise StravaError("Save your Strava Client ID and Secret first.")

    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": s.strava_client_id,
            "client_secret": s.strava_client_secret,
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise StravaError(f"Strava authorization failed: {resp.status_code} {resp.text}")

    data = resp.json()
    s.strava_access_token = data["access_token"]
    s.strava_refresh_token = data["refresh_token"]
    s.strava_token_expires_at = data["expires_at"]
    db.commit()


def _get_access_token(db: Session) -> str:
    s = get_settings(db)

    if not (s.strava_client_id and s.strava_client_secret and s.strava_refresh_token):
        raise StravaError("Strava isn't connected yet. Go to /settings and connect it.")

    now = time.time()
    if s.strava_access_token and s.strava_token_expires_at and s.strava_token_expires_at > now + 60:
        return s.strava_access_token

    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": s.strava_client_id,
            "client_secret": s.strava_client_secret,
            "refresh_token": s.strava_refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise StravaError(f"Strava token refresh failed: {resp.status_code} {resp.text}")

    data = resp.json()
    s.strava_access_token = data["access_token"]
    s.strava_refresh_token = data["refresh_token"]
    s.strava_token_expires_at = data["expires_at"]
    db.commit()
    return s.strava_access_token


def fetch_segment(db: Session, segment_id: int) -> dict:
    token = _get_access_token(db)
    resp = requests.get(
        f"{API_BASE}/segments/{segment_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    if resp.status_code == 404:
        raise StravaError(f"Segment {segment_id} not found (or not visible to this Strava account).")
    if resp.status_code == 401:
        raise StravaError("Strava rejected the access token. Try reconnecting Strava in /settings.")
    if resp.status_code != 200:
        raise StravaError(f"Strava API error {resp.status_code}: {resp.text}")
    return resp.json()
