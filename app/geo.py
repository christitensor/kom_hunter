"""Segment metadata and place lookups that don't need the Strava API.

Strava's segment page only ships full geometry (polyline, start/end
coordinates) to a *logged-in* session -- there's no public, unauthenticated
way to get that without impersonating a Strava account. Rather than scrape
around that, segments are entered manually (name + two coordinates you can
read straight off any map), and this module only helps pre-fill the parts of
that form that Strava *does* publish anonymously -- name, distance,
elevation, grade, and rough place name -- via Strava's public
embeddable-widget page, which needs no auth or app registration. Place
lookups (a city name for a pair of coordinates, or coordinates for a place
name) go through Open-Meteo/OpenStreetMap, both free and keyless.
"""

import html
import re

import requests

USER_AGENT = "kom-hunter (personal segment tracker; contact via GitHub issues)"

_SEGMENT_ID_RE = re.compile(r"strava\.com/segments/(\d+)")
_TITLE_RE = re.compile(r"<h1>\s*<a[^>]*>([^<]+)</a>")
_LOCATION_RE = re.compile(r"</h1>\s*([^<]+?)\s*<ul")
_STAT_RE = re.compile(
    r"<div class='span stat-subtext'>\s*(\w+)\s*</div>\s*<b class='stat-text'>\s*([^<]+?)\s*</b>",
    re.IGNORECASE,
)


class LookupError(RuntimeError):
    pass


def parse_segment_id(url_or_id: str) -> int | None:
    text = (url_or_id or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    match = _SEGMENT_ID_RE.search(text)
    return int(match.group(1)) if match else None


def lookup_public_segment(url_or_id: str) -> dict:
    """Best-effort autofill from Strava's public embed widget -- no OAuth,
    no API key, no connected account. Returns whatever it could parse; a
    field missing from the result just means the "Add segment" form leaves
    that input blank for the user to fill in by hand.
    """
    segment_id = parse_segment_id(url_or_id)
    if segment_id is None:
        raise LookupError(
            f"Couldn't find a segment id in '{url_or_id}'. Paste a link like "
            "https://www.strava.com/segments/12345678, or just fill the form in by hand."
        )

    try:
        resp = requests.get(
            f"https://www.strava.com/segments/{segment_id}/embed",
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
    except requests.RequestException as e:
        raise LookupError(f"Couldn't reach Strava: {e}") from e

    if resp.status_code == 404:
        raise LookupError(f"Segment {segment_id} isn't public (or doesn't exist).")
    if resp.status_code != 200:
        raise LookupError(f"Strava returned {resp.status_code} fetching that segment.")

    body = resp.text
    result: dict = {"strava_id": segment_id, "url": f"https://www.strava.com/segments/{segment_id}"}

    title_match = _TITLE_RE.search(body)
    if title_match:
        result["name"] = html.unescape(title_match.group(1)).strip()

    location_match = _LOCATION_RE.search(body)
    if location_match:
        result["city"] = html.unescape(location_match.group(1)).strip()

    for label, value in _STAT_RE.findall(body):
        label = label.lower()
        num_match = re.search(r"[\d.]+", value)
        if not num_match:
            continue
        num = float(num_match.group())
        if label == "distance":
            result["distance_m"] = num * 1000 if "km" in value.lower() else num
        elif label == "elevation":
            result["elevation_gain_m"] = num
        elif label == "grade":
            result["average_grade"] = num

    return result


def _geocode_query(query: str) -> dict | None:
    try:
        resp = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": query, "count": 1},
            timeout=8,
        )
        resp.raise_for_status()
        results = resp.json().get("results") or []
    except (requests.RequestException, ValueError):
        return None
    if not results:
        return None
    top = results[0]
    return {"lat": top["latitude"], "lng": top["longitude"]}


def geocode_place(name: str) -> dict | None:
    """Forward geocode a place name to coordinates via Open-Meteo (free, no
    key). Used only to center the "pick your start/end point" map -- never
    stored as the segment's actual location.

    Open-Meteo's geocoder wants a plain place name, not a full address --
    "Marin Headlands (GGNRA), USA" comes back empty but "Marin Headlands"
    matches fine. So it's tried as-is first, then with anything in
    parentheses and everything after the first comma stripped off.
    """
    if not name:
        return None
    candidates = [name]
    stripped = re.sub(r"\([^)]*\)", "", name).split(",")[0].strip()
    if stripped and stripped not in candidates:
        candidates.append(stripped)
    for candidate in candidates:
        result = _geocode_query(candidate)
        if result:
            return result
    return None


def reverse_geocode_city(lat: float, lng: float) -> str | None:
    """Best-effort city name for a coordinate, via OpenStreetMap Nominatim
    (free, no key). Only used to pre-fill the city field when a segment is
    added without one -- never required, since the user can always type
    their own grouping name instead.
    """
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"format": "jsonv2", "lat": lat, "lon": lng, "zoom": 10},
            headers={"User-Agent": USER_AGENT},
            timeout=8,
        )
        resp.raise_for_status()
        address = resp.json().get("address") or {}
    except (requests.RequestException, ValueError):
        return None

    city = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("county")
    )
    state = address.get("state")
    if city and state:
        return f"{city}, {state}"
    return city or state
