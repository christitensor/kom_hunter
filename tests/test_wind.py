import math

from app import wind


def test_bearing_due_north():
    d = wind.route_direction(0.0, 0.0, 1.0, 0.0, None)
    assert abs(d.bearing_deg - 0.0) < 0.5
    assert d.consistency > 0.99


def test_bearing_due_east():
    d = wind.route_direction(0.0, 0.0, 0.0, 1.0, None)
    assert abs(d.bearing_deg - 90.0) < 0.5


def test_ideal_wind_from_is_opposite_of_travel():
    assert wind.ideal_wind_from_deg(0) == 180
    assert wind.ideal_wind_from_deg(90) == 270
    assert wind.ideal_wind_from_deg(270) == 90


def test_tailwind_component_pure_tailwind():
    # Travelling due north (bearing 0), wind FROM the south (180) blows you north: pure tailwind.
    tw = wind.tailwind_component(wind_speed=20, wind_from_deg=180, travel_bearing_deg=0)
    assert abs(tw - 20) < 1e-6


def test_tailwind_component_pure_headwind():
    # Wind FROM the north (0) while travelling north: straight headwind.
    tw = wind.tailwind_component(wind_speed=20, wind_from_deg=0, travel_bearing_deg=0)
    assert abs(tw - (-20)) < 1e-6


def test_tailwind_component_pure_crosswind_is_zero():
    tw = wind.tailwind_component(wind_speed=20, wind_from_deg=90, travel_bearing_deg=0)
    assert abs(tw) < 1e-6


def test_crosswind_component_matches_pure_crosswind_case():
    cw = wind.crosswind_component(wind_speed=20, wind_from_deg=90, travel_bearing_deg=0)
    assert abs(abs(cw) - 20) < 1e-6


def test_wind_sensitivity_flat_long_is_high():
    s = wind.wind_sensitivity(average_grade_pct=1.0, distance_m=3000)
    assert s > 0.8


def test_wind_sensitivity_steep_short_is_low():
    s = wind.wind_sensitivity(average_grade_pct=12.0, distance_m=400)
    assert s < 0.3


def test_wind_sensitivity_bounded():
    for grade in (-20, 0, 5, 25):
        for dist in (10, 500, 5000, 50000):
            s = wind.wind_sensitivity(grade, dist)
            assert 0.0 <= s <= 1.0


def test_route_direction_switchback_has_lower_consistency_than_straight_line():
    # Zig-zag climb: each leg is 45 deg off the net direction, so vector-sum
    # consistency should be well below a straight line's 1.0 (cos(45) ~ 0.71).
    points = [(0.0, 0.0), (0.01, 0.01), (0.02, 0.0), (0.03, 0.01), (0.04, 0.0)]
    import polyline as polyline_lib

    encoded = polyline_lib.encode(points)
    d = wind.route_direction(points[0][0], points[0][1], points[-1][0], points[-1][1], encoded)
    assert 0.5 < d.consistency < 0.9

    straight = wind.route_direction(0.0, 0.0, 1.0, 0.0, None)
    assert d.consistency < straight.consistency


def test_compass_label_cardinal_points():
    assert wind.compass_label(0) == "N"
    assert wind.compass_label(90) == "E"
    assert wind.compass_label(180) == "S"
    assert wind.compass_label(270) == "W"
