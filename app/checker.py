import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import analysis, telegram, weather
from app.config import FORECAST_DAYS
from app.db import Notification, Segment

logger = logging.getLogger("kom_hunter.checker")

# Only alert on the single best qualifying window per day per segment, so a
# multi-day gusty spell doesn't turn into hourly spam.
_MAX_ALERTS_PER_SEGMENT_PER_RUN = 5


def check_segment(db: Session, segment: Segment) -> list[analysis.PeakWindow]:
    mid_lat = (segment.start_lat + segment.end_lat) / 2
    mid_lng = (segment.start_lng + segment.end_lng) / 2

    forecast = weather.get_forecast(mid_lat, mid_lng, FORECAST_DAYS)
    baseline = weather.get_historical_baseline(mid_lat, mid_lng)

    windows = analysis.find_peak_windows(
        forecast=forecast,
        baseline=baseline,
        bearing_deg=segment.bearing_deg,
        wind_sensitivity=segment.wind_sensitivity,
    )

    # Keep only the best window per calendar day.
    best_per_day: dict[str, analysis.PeakWindow] = {}
    for w in windows:
        day_key = w.time.strftime("%Y-%m-%d")
        if day_key not in best_per_day or w.peak_score > best_per_day[day_key].peak_score:
            best_per_day[day_key] = w

    newly_notified = []
    for w in sorted(best_per_day.values(), key=lambda w: w.peak_score, reverse=True):
        if len(newly_notified) >= _MAX_ALERTS_PER_SEGMENT_PER_RUN:
            break

        already = db.execute(
            select(Notification).where(
                Notification.segment_id == segment.id,
                Notification.forecast_time == w.time,
            )
        ).scalar_one_or_none()
        if already:
            continue

        try:
            telegram.send_message(db, telegram.format_peak_alert(segment.name, segment.url, w))
        except Exception:
            logger.exception("Failed to send Telegram alert for segment %s", segment.id)
            continue

        db.add(
            Notification(
                segment_id=segment.id,
                forecast_time=w.time,
                peak_score=w.peak_score,
                tailwind_mph=w.tailwind_mph,
            )
        )
        db.commit()
        newly_notified.append(w)

    return newly_notified


def check_all_segments(db: Session) -> dict[int, list[analysis.PeakWindow]]:
    segments = db.execute(select(Segment).where(Segment.active.is_(True))).scalars().all()
    results = {}
    for segment in segments:
        try:
            results[segment.id] = check_segment(db, segment)
        except Exception:
            logger.exception("Failed to check segment %s (%s)", segment.id, segment.name)
    return results
