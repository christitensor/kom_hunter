"""Segment geometry and wind-benefit math.

Everything here is a physically-reasoned heuristic, not a full aero/power
simulation (that would need rider CdA, weight, and power curve). The goal is
a directionally-correct answer: which way the wind should blow, and how much
a segment's terrain lets that wind actually matter.
"""

import math
from dataclasses import dataclass

import polyline as polyline_lib


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial great-circle bearing from point 1 to point 2, degrees 0-360."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    x = math.sin(dlambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    theta = math.atan2(x, y)
    return (math.degrees(theta) + 360) % 360


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass
class RouteDirection:
    bearing_deg: float
    consistency: float  # 0-1, 1 = perfectly straight


def route_direction(
    start_lat: float, start_lng: float, end_lat: float, end_lng: float, encoded_polyline: str | None
) -> RouteDirection:
    """Distance-weighted dominant bearing of the segment.

    If a polyline is available we walk each leg, weight its unit bearing
    vector by leg length, and vector-sum. The magnitude of that sum relative
    to total distance tells us how "straight" the route is: a segment that
    switchbacks up a climb sums to near zero even though each leg is long,
    which correctly signals that a single wind direction won't help evenly
    along the whole thing. Falls back to a straight start->end bearing if no
    polyline is available.
    """
    points = []
    if encoded_polyline:
        try:
            points = polyline_lib.decode(encoded_polyline)
        except Exception:
            points = []

    if len(points) < 2:
        bearing = _bearing_deg(start_lat, start_lng, end_lat, end_lng)
        return RouteDirection(bearing_deg=bearing, consistency=1.0)

    sum_x, sum_y, total_dist = 0.0, 0.0, 0.0
    for (lat1, lon1), (lat2, lon2) in zip(points, points[1:]):
        dist = _haversine_m(lat1, lon1, lat2, lon2)
        if dist < 0.5:
            continue
        b = math.radians(_bearing_deg(lat1, lon1, lat2, lon2))
        sum_x += dist * math.sin(b)
        sum_y += dist * math.cos(b)
        total_dist += dist

    if total_dist == 0:
        bearing = _bearing_deg(start_lat, start_lng, end_lat, end_lng)
        return RouteDirection(bearing_deg=bearing, consistency=1.0)

    bearing = (math.degrees(math.atan2(sum_x, sum_y)) + 360) % 360
    magnitude = math.hypot(sum_x, sum_y)
    consistency = max(0.0, min(1.0, magnitude / total_dist))
    return RouteDirection(bearing_deg=bearing, consistency=consistency)


def ideal_wind_from_deg(travel_bearing_deg: float) -> float:
    """Meteorological wind-FROM direction that gives a pure tailwind."""
    return (travel_bearing_deg + 180) % 360


def wind_sensitivity(average_grade_pct: float, distance_m: float) -> float:
    """0-1 heuristic for how much aero (wind) matters vs gravity/grinding.

    Steep climbs are slow and gravity-dominated: even a strong tailwind
    saves relatively little time. Flat/rolling segments are fast, so
    aerodynamic drag -- and therefore wind -- dominates the time difference.
    Very short segments also dilute wind's effect (less time exposed).
    """
    grade = abs(average_grade_pct)
    grade_factor = max(0.15, 1.0 - grade / 12.0)  # ~0 sensitivity by grade 12%+, floor 0.15
    length_factor = min(1.0, distance_m / 1500.0)  # ramps up to full weight by 1.5km
    return round(max(0.1, min(1.0, grade_factor * (0.5 + 0.5 * length_factor))), 3)


def tailwind_component(wind_speed: float, wind_from_deg: float, travel_bearing_deg: float) -> float:
    """Positive = tailwind, negative = headwind, component along direction of travel.

    Unit-agnostic: returns the same speed unit passed in.
    """
    blowing_towards_deg = (wind_from_deg + 180) % 360
    angle = math.radians(blowing_towards_deg - travel_bearing_deg)
    return wind_speed * math.cos(angle)


def crosswind_component(wind_speed: float, wind_from_deg: float, travel_bearing_deg: float) -> float:
    blowing_towards_deg = (wind_from_deg + 180) % 360
    angle = math.radians(blowing_towards_deg - travel_bearing_deg)
    return wind_speed * math.sin(angle)


def compass_label(deg: float) -> str:
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    idx = round((deg % 360) / 22.5) % 16
    return dirs[idx]
