import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import geo, wind
from app.db import DEFAULT_CITY, Segment


class SegmentInputError(RuntimeError):
    pass


def _unique_strava_id(db: Session) -> int:
    """A synthetic id for segments added without a Strava link, kept in a
    range real Strava segment ids (all positive, currently well under 1e9)
    never reach, so it can share the same unique column without colliding.
    """
    for _ in range(10):
        candidate = -secrets.randbelow(2**31)
        exists = db.execute(select(Segment.id).where(Segment.strava_id == candidate)).first()
        if not exists:
            return candidate
    raise SegmentInputError("Couldn't allocate an id for this segment -- try again.")


def add_segment_manual(db: Session, data: dict) -> Segment:
    name = (data.get("name") or "").strip()
    if not name:
        raise SegmentInputError("Segment name is required.")

    try:
        start_lat, start_lng = float(data["start_lat"]), float(data["start_lng"])
        end_lat, end_lng = float(data["end_lat"]), float(data["end_lng"])
    except (KeyError, TypeError, ValueError):
        raise SegmentInputError("Start and end coordinates are required.")

    url = (data.get("url") or "").strip()
    strava_id = geo.parse_segment_id(url) if url else None
    if strava_id is not None:
        existing = db.execute(select(Segment).where(Segment.strava_id == strava_id)).scalar_one_or_none()
        if existing:
            return existing
    else:
        strava_id = _unique_strava_id(db)

    distance_m = data.get("distance_m")
    if not distance_m:
        distance_m = wind.haversine_m(start_lat, start_lng, end_lat, end_lng)
    distance_m = float(distance_m)

    average_grade = float(data.get("average_grade") or 0.0)
    max_grade = float(data.get("max_grade") or average_grade)
    elevation_gain_m = float(data.get("elevation_gain_m") or 0.0)

    city = (data.get("city") or "").strip()
    if not city:
        city = geo.reverse_geocode_city(start_lat, start_lng) or DEFAULT_CITY

    direction = wind.route_direction(start_lat, start_lng, end_lat, end_lng, None)
    sensitivity = wind.wind_sensitivity(average_grade, distance_m)

    if not url and strava_id > 0:
        url = f"https://www.strava.com/segments/{strava_id}"

    segment = Segment(
        strava_id=strava_id,
        name=name,
        url=url,
        city=city,
        distance_m=distance_m,
        average_grade=average_grade,
        maximum_grade=max_grade,
        elevation_gain_m=elevation_gain_m,
        climb_category=0,
        start_lat=start_lat,
        start_lng=start_lng,
        end_lat=end_lat,
        end_lng=end_lng,
        bearing_deg=direction.bearing_deg,
        bearing_consistency=direction.consistency,
        ideal_wind_from_deg=wind.ideal_wind_from_deg(direction.bearing_deg),
        wind_sensitivity=sensitivity,
    )
    db.add(segment)
    db.commit()
    db.refresh(segment)
    return segment


def segment_summary(segment: Segment) -> dict:
    return {
        "id": segment.id,
        "strava_id": segment.strava_id,
        "name": segment.name,
        "url": segment.url,
        "city": segment.city,
        "distance_m": segment.distance_m,
        "distance_mi": round(segment.distance_m / 1609.34, 2),
        "average_grade": segment.average_grade,
        "maximum_grade": segment.maximum_grade,
        "elevation_gain_m": segment.elevation_gain_m,
        "climb_category": segment.climb_category,
        "bearing_deg": round(segment.bearing_deg, 1),
        "bearing_compass": wind.compass_label(segment.bearing_deg),
        "bearing_consistency": segment.bearing_consistency,
        "ideal_wind_from_deg": round(segment.ideal_wind_from_deg, 1),
        "ideal_wind_from_compass": wind.compass_label(segment.ideal_wind_from_deg),
        "wind_sensitivity": segment.wind_sensitivity,
        "active": segment.active,
    }
