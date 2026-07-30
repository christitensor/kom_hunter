import re
import time

import requests

from app.config import STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN

TOKEN_URL = "https://www.strava.com/oauth/token"
API_BASE = "https://www.strava.com/api/v3"

_SEGMENT_URL_RE = re.compile(r"strava\.com/segments/(\d+)")

_token_cache: dict = {"access_token": None, "expires_at": 0}


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


def _get_access_token() -> str:
    now = time.time()
    if _token_cache["access_token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["access_token"]

    if not (STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET and STRAVA_REFRESH_TOKEN):
        raise StravaError(
            "Strava credentials are not configured. Set STRAVA_CLIENT_ID, "
            "STRAVA_CLIENT_SECRET and STRAVA_REFRESH_TOKEN (see scripts/get_strava_token.py)."
        )

    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": STRAVA_CLIENT_ID,
            "client_secret": STRAVA_CLIENT_SECRET,
            "refresh_token": STRAVA_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise StravaError(f"Strava token refresh failed: {resp.status_code} {resp.text}")

    data = resp.json()
    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"] = data["expires_at"]
    return data["access_token"]


def fetch_segment(segment_id: int) -> dict:
    token = _get_access_token()
    resp = requests.get(
        f"{API_BASE}/segments/{segment_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    if resp.status_code == 404:
        raise StravaError(f"Segment {segment_id} not found (or not visible to this Strava account).")
    if resp.status_code == 401:
        raise StravaError("Strava rejected the access token. Check your refresh token / app credentials.")
    if resp.status_code != 200:
        raise StravaError(f"Strava API error {resp.status_code}: {resp.text}")
    return resp.json()
