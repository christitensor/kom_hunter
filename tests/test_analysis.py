from datetime import datetime, timedelta

from app import analysis
from app.weather import HourlyReading

# Segment travels due north (bearing 0), so a pure tailwind is wind FROM the south (180).
BEARING = 0.0
BASE_TIME = datetime(2026, 8, 1, 12, 0)


def make_baseline(n=24 * 60, speed=5.0, from_deg=180.0):
    return [
        HourlyReading(
            time=BASE_TIME - timedelta(hours=i),
            wind_speed_mph=speed,
            wind_from_deg=from_deg,
            wind_gust_mph=speed + 3,
            precipitation_probability=0,
            temperature_f=65,
        )
        for i in range(n)
    ]


def reading(hours_ahead, speed, from_deg, gust=None, precip=0.0, temp=65.0):
    return HourlyReading(
        time=BASE_TIME + timedelta(hours=hours_ahead),
        wind_speed_mph=speed,
        wind_from_deg=from_deg,
        wind_gust_mph=gust if gust is not None else speed + 3,
        precipitation_probability=precip,
        temperature_f=temp,
    )


def test_no_baseline_variance_still_flags_a_real_gust():
    baseline = make_baseline(speed=5.0)  # dead calm typical conditions, no variance
    forecast = [reading(1, speed=20.0, from_deg=180.0)]  # big tailwind gust, well above typical
    windows = analysis.find_peak_windows(forecast, baseline, BEARING, wind_sensitivity=1.0)
    assert len(windows) == 1
    assert windows[0].tailwind_mph > 15

def test_typical_day_does_not_qualify():
    baseline = make_baseline(speed=12.0, from_deg=180.0)
    forecast = [reading(1, speed=12.0, from_deg=180.0)]  # exactly average
    windows = analysis.find_peak_windows(forecast, baseline, BEARING, wind_sensitivity=1.0)
    assert windows == []


def test_light_wind_never_qualifies_even_if_unusual():
    # Baseline is essentially windless, so any breeze is a huge z-score outlier,
    # but it's still too light in absolute terms to matter for a KOM.
    baseline = make_baseline(speed=0.5, from_deg=180.0)
    forecast = [reading(1, speed=5.0, from_deg=180.0)]
    windows = analysis.find_peak_windows(forecast, baseline, BEARING, wind_sensitivity=1.0)
    assert windows == []


def test_headwind_never_qualifies():
    baseline = make_baseline(speed=5.0, from_deg=180.0)
    forecast = [reading(1, speed=20.0, from_deg=0.0)]  # wind FROM the north = headwind when heading north
    windows = analysis.find_peak_windows(forecast, baseline, BEARING, wind_sensitivity=1.0)
    assert windows == []


def test_dangerous_gusts_are_excluded_despite_good_tailwind():
    baseline = make_baseline(speed=5.0, from_deg=180.0)
    forecast = [reading(1, speed=20.0, from_deg=180.0, gust=45.0)]
    windows = analysis.find_peak_windows(forecast, baseline, BEARING, wind_sensitivity=1.0)
    assert windows == []


def test_rain_excludes_an_otherwise_perfect_window():
    baseline = make_baseline(speed=5.0, from_deg=180.0)
    forecast = [reading(1, speed=20.0, from_deg=180.0, precip=60.0)]
    windows = analysis.find_peak_windows(forecast, baseline, BEARING, wind_sensitivity=1.0)
    assert windows == []


def test_low_wind_sensitivity_reduces_score_but_can_still_qualify():
    baseline = make_baseline(speed=5.0, from_deg=180.0)
    forecast = [reading(1, speed=25.0, from_deg=180.0)]
    high_sens = analysis.find_peak_windows(forecast, baseline, BEARING, wind_sensitivity=1.0)
    low_sens = analysis.find_peak_windows(forecast, baseline, BEARING, wind_sensitivity=0.2)
    assert high_sens[0].peak_score >= low_sens[0].peak_score
    assert "steep/technical" in low_sens[0].reason


def test_results_sorted_best_first():
    baseline = make_baseline(speed=5.0, from_deg=180.0)
    forecast = [
        reading(1, speed=15.0, from_deg=180.0),
        reading(2, speed=25.0, from_deg=180.0),
        reading(3, speed=18.0, from_deg=180.0),
    ]
    windows = analysis.find_peak_windows(forecast, baseline, BEARING, wind_sensitivity=1.0)
    scores = [w.peak_score for w in windows]
    assert scores == sorted(scores, reverse=True)
