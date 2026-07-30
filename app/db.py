from datetime import datetime

from sqlalchemy import create_engine, Boolean, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import DATABASE_URL, ENGINE_KWARGS


class Base(DeclarativeBase):
    pass


class Segment(Base):
    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strava_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(String)

    distance_m: Mapped[float] = mapped_column(Float)
    average_grade: Mapped[float] = mapped_column(Float)
    maximum_grade: Mapped[float] = mapped_column(Float)
    elevation_gain_m: Mapped[float] = mapped_column(Float)
    climb_category: Mapped[int] = mapped_column(Integer, default=0)

    start_lat: Mapped[float] = mapped_column(Float)
    start_lng: Mapped[float] = mapped_column(Float)
    end_lat: Mapped[float] = mapped_column(Float)
    end_lng: Mapped[float] = mapped_column(Float)

    # Distance-weighted dominant direction of travel, degrees 0-360 (0 = N).
    bearing_deg: Mapped[float] = mapped_column(Float)
    # 0-1, how consistent that bearing is along the route (1 = dead straight).
    bearing_consistency: Mapped[float] = mapped_column(Float)
    # Ideal wind-FROM direction (meteorological convention) for a tailwind, degrees.
    ideal_wind_from_deg: Mapped[float] = mapped_column(Float)
    # 0-1 heuristic: how much a tailwind actually matters here (flat/fast vs steep/slow).
    wind_sensitivity: Mapped[float] = mapped_column(Float)

    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("strava_id", name="uq_segment_strava_id"),)


class Notification(Base):
    """Tracks which forecast windows we've already alerted on, so we don't spam."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    segment_id: Mapped[int] = mapped_column(Integer, index=True)
    forecast_time: Mapped[datetime] = mapped_column(DateTime)
    peak_score: Mapped[float] = mapped_column(Float)
    tailwind_mph: Mapped[float] = mapped_column(Float)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("segment_id", "forecast_time", name="uq_notification_window"),)


class AppSettings(Base):
    """Singleton row (id=1) holding credentials, editable from the /settings page.

    Kept in the DB rather than env vars so the whole setup flow -- connecting
    Strava, wiring up Telegram -- can happen by tapping around the deployed
    site instead of touching a hosting dashboard.
    """

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    strava_client_id: Mapped[str | None] = mapped_column(String, nullable=True)
    strava_client_secret: Mapped[str | None] = mapped_column(String, nullable=True)
    strava_access_token: Mapped[str | None] = mapped_column(String, nullable=True)
    strava_refresh_token: Mapped[str | None] = mapped_column(String, nullable=True)
    strava_token_expires_at: Mapped[int | None] = mapped_column(Integer, nullable=True)

    telegram_bot_token: Mapped[str | None] = mapped_column(String, nullable=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String, nullable=True)


engine = create_engine(DATABASE_URL, **ENGINE_KWARGS)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_settings(db) -> AppSettings:
    settings = db.get(AppSettings, 1)
    if settings is None:
        settings = AppSettings(id=1)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings
