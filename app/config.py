import os

from dotenv import load_dotenv

load_dotenv()


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


# True when running as a Vercel serverless function (Vercel sets this itself).
IS_VERCEL = bool(os.getenv("VERCEL"))

# Checked against Vercel Cron's Authorization header on /api/cron/check-segments.
CRON_SECRET = os.getenv("CRON_SECRET", "")

# Gate for /settings and its API -- lets you share the segment tracker
# without exposing your Strava/Telegram credentials to whoever has the link.
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

CHECK_INTERVAL_HOURS = _int_env("CHECK_INTERVAL_HOURS", 3)
FORECAST_DAYS = _int_env("FORECAST_DAYS", 7)

# Only hours you can actually go ride matter -- restricts peak-window
# detection (and what counts as "typical" wind for the z-score baseline) to
# this local-time window. Weekday default 4pm-8pm; weekend default 8am-8pm
# (Saturday/Sunday), since there's no after-work constraint on those days.
RIDE_WINDOW_START_HOUR = _int_env("RIDE_WINDOW_START_HOUR", 16)
RIDE_WINDOW_END_HOUR = _int_env("RIDE_WINDOW_END_HOUR", 20)
WEEKEND_RIDE_WINDOW_START_HOUR = _int_env("WEEKEND_RIDE_WINDOW_START_HOUR", 8)
WEEKEND_RIDE_WINDOW_END_HOUR = _int_env("WEEKEND_RIDE_WINDOW_END_HOUR", 20)

# Local dev / self-hosted default: a SQLite file next to the project.
# On Vercel, DATABASE_URL is injected by the Neon (Postgres) storage integration.
_raw_database_url = os.getenv("DATABASE_URL")

if _raw_database_url:
    # Neon/most providers hand out "postgres://" or "postgresql://"; SQLAlchemy
    # needs an explicit driver so it picks psycopg (installed via requirements.txt).
    DATABASE_URL = _raw_database_url.replace("postgres://", "postgresql+psycopg://", 1).replace(
        "postgresql://", "postgresql+psycopg://", 1
    )
    ENGINE_KWARGS = {"pool_pre_ping": True}
else:
    DATABASE_PATH = os.getenv("DATABASE_PATH", "./kom_hunter.db")
    DATABASE_URL = f"sqlite:///{DATABASE_PATH}"
    ENGINE_KWARGS = {"connect_args": {"check_same_thread": False}}
