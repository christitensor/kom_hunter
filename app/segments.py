from sqlalchemy import select
from sqlalchemy.orm import Session

from app import strava, wind
from app.db import Segment


def add_segment(db: Session, url_or_id: str) -> Segment:
    segment_id = strava.parse_segment_id(url_or_id)

    existing = db.execute(select(Segment).where(Segment.strava_id == segment_id)).scalar_one_or_none()
    if existing:
        return existing

    data = strava.fetch_segment(segment_id)

    start_lat, start_lng = data["start_latlng"]
    end_lat, end_lng = data["end_latlng"]
    encoded_polyline = (data.get("map") or {}).get("polyline")

    direction = wind.route_direction(start_lat, start_lng, end_lat, end_lng, encoded_polyline)
    sensitivity = wind.wind_sensitivity(data["average_grade"], data["distance"])

    segment = Segment(
        strava_id=segment_id,
        name=data["name"],
        url=f"https://www.strava.com/segments/{segment_id}",
        distance_m=data["distance"],
        average_grade=data["average_grade"],
        maximum_grade=data["maximum_grade"],
        elevation_gain_m=data.get("total_elevation_gain", 0.0),
        climb_category=data.get("climb_category", 0),
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
