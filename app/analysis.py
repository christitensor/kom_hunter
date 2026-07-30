"""Turns a segment's geometry + a weather forecast into a ranked list of
'this is a peak-tailwind window, go hunt the KOM' alerts.

'Peak' is deliberately defined relative to what's typical at that spot, not
an arbitrary global constant, using a rolling ~60 day local baseline:
  - Tailwind component must be a genuine outlier vs. the local baseline
    (z-score), not just any old breeze.
  - It must also clear an absolute floor in mph, so a location with almost
    no wind ever doesn't get "peak" alerts for a light draft.
  - Sustained wind/gusts are capped for rideability/safety -- a dangerous
    gale is not a "good" KOM day even if the tailwind component is huge.
  - Rain is excluded -- wet pavement erases any aero gain.
"""

import statistics
from dataclasses import dataclass
from datetime import datetime

from app import wind
from app.weather import HourlyReading

MIN_TAILWIND_MPH = 10.0
MIN_Z_SCORE = 1.25
MAX_SAFE_WIND_MPH = 28.0
MAX_SAFE_GUST_MPH = 38.0
MAX_PRECIP_PROBABILITY = 30.0


@dataclass
class PeakWindow:
    time: datetime
    tailwind_mph: float
    wind_speed_mph: float
    wind_gust_mph: float
    wind_from_deg: float
    z_score: float
    effective_tailwind_mph: float
    peak_score: float
    precipitation_probability: float | None
    temperature_f: float | None
    reason: str


def _baseline_stats(readings: list[HourlyReading], bearing_deg: float) -> tuple[float, float]:
    values = [wind.tailwind_component(r.wind_speed_mph, r.wind_from_deg, bearing_deg) for r in readings]
    if len(values) < 10:
        return 0.0, 1.0  # not enough history to be meaningful; z-score becomes ~raw value
    mean = statistics.fmean(values)
    stdev = statistics.pstdev(values) or 1.0
    return mean, stdev


def find_peak_windows(
    forecast: list[HourlyReading],
    baseline: list[HourlyReading],
    bearing_deg: float,
    wind_sensitivity: float,
) -> list[PeakWindow]:
    baseline_mean, baseline_std = _baseline_stats(baseline, bearing_deg)

    windows: list[PeakWindow] = []
    for r in forecast:
        tailwind = wind.tailwind_component(r.wind_speed_mph, r.wind_from_deg, bearing_deg)
        z = (tailwind - baseline_mean) / baseline_std

        if r.precipitation_probability is not None and r.precipitation_probability > MAX_PRECIP_PROBABILITY:
            continue
        if r.wind_speed_mph > MAX_SAFE_WIND_MPH or r.wind_gust_mph > MAX_SAFE_GUST_MPH:
            continue
        if tailwind < MIN_TAILWIND_MPH:
            continue
        if z < MIN_Z_SCORE:
            continue

        effective_tailwind = tailwind * wind_sensitivity
        z_norm = max(0.0, min(1.0, z / 3.0))
        tw_norm = max(0.0, min(1.0, effective_tailwind / 18.0))
        peak_score = round(0.5 * z_norm + 0.5 * tw_norm, 3)

        reason = (
            f"{tailwind:.0f} mph tailwind ({z:.1f}σ above the usual wind here), "
            f"{r.wind_speed_mph:.0f} mph sustained from {wind.compass_label(r.wind_from_deg)}"
        )
        if wind_sensitivity < 0.4:
            reason += " -- note: steep/technical segment, so gravity blunts some of this benefit"

        windows.append(
            PeakWindow(
                time=r.time,
                tailwind_mph=round(tailwind, 1),
                wind_speed_mph=r.wind_speed_mph,
                wind_gust_mph=r.wind_gust_mph,
                wind_from_deg=r.wind_from_deg,
                z_score=round(z, 2),
                effective_tailwind_mph=round(effective_tailwind, 1),
                peak_score=peak_score,
                precipitation_probability=r.precipitation_probability,
                temperature_f=r.temperature_f,
                reason=reason,
            )
        )

    windows.sort(key=lambda w: w.peak_score, reverse=True)
    return windows
