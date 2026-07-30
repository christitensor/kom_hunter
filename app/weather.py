"""Weather via Open-Meteo (free, no API key required)."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import requests

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

HOURLY_FIELDS = "windspeed_10m,winddirection_10m,windgusts_10m,precipitation_probability,temperature_2m"


class WeatherError(RuntimeError):
    pass


@dataclass
class HourlyReading:
    time: datetime
    wind_speed_mph: float
    wind_from_deg: float
    wind_gust_mph: float
    precipitation_probability: float | None
    temperature_f: float | None


def _parse_hourly(payload: dict, has_precip: bool = True, has_temp: bool = True) -> list[HourlyReading]:
    hourly = payload.get("hourly", {})
    times = hourly.get("time", [])
    speeds = hourly.get("windspeed_10m", [])
    dirs = hourly.get("winddirection_10m", [])
    gusts = hourly.get("windgusts_10m", [None] * len(times))
    precip = hourly.get("precipitation_probability", [None] * len(times)) if has_precip else [None] * len(times)
    temps = hourly.get("temperature_2m", [None] * len(times)) if has_temp else [None] * len(times)

    readings = []
    for t, spd, wd, g, p, tp in zip(times, speeds, dirs, gusts, precip, temps):
        if spd is None or wd is None:
            continue
        readings.append(
            HourlyReading(
                time=datetime.fromisoformat(t),
                wind_speed_mph=spd,
                wind_from_deg=wd,
                wind_gust_mph=g if g is not None else spd,
                precipitation_probability=p,
                temperature_f=tp,
            )
        )
    return readings


def get_forecast(lat: float, lon: float, days: int) -> list[HourlyReading]:
    resp = requests.get(
        FORECAST_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "hourly": HOURLY_FIELDS,
            "forecast_days": max(1, min(days, 16)),
            "windspeed_unit": "mph",
            "temperature_unit": "fahrenheit",
            "timezone": "auto",
        },
        timeout=20,
    )
    if resp.status_code != 200:
        raise WeatherError(f"Open-Meteo forecast error {resp.status_code}: {resp.text}")
    return _parse_hourly(resp.json())


def get_historical_baseline(lat: float, lon: float, lookback_days: int = 60) -> list[HourlyReading]:
    """Past ~2 months of actual hourly wind, used to define what 'typical' looks like here."""
    end = date.today() - timedelta(days=2)  # archive API lags a couple days
    start = end - timedelta(days=lookback_days)
    resp = requests.get(
        ARCHIVE_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "hourly": "windspeed_10m,winddirection_10m",
            "windspeed_unit": "mph",
            "timezone": "auto",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise WeatherError(f"Open-Meteo archive error {resp.status_code}: {resp.text}")
    return _parse_hourly(resp.json(), has_precip=False, has_temp=False)
