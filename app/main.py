import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import analysis, auth, checker, segments, strava, telegram, weather
from app.config import CRON_SECRET, FORECAST_DAYS, IS_VERCEL
from app.db import AppSettings, Segment, SessionLocal, get_settings, init_db
from app.strava import StravaError
from app.weather import WeatherError

logging.basicConfig(level=logging.INFO)

_scheduler_handle = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    global _scheduler_handle
    if not IS_VERCEL:
        # Serverless deployments use a Vercel Cron hitting /api/cron/check-segments
        # instead; an in-process background loop wouldn't survive between
        # invocations there anyway.
        from app.scheduler import start_scheduler

        _scheduler_handle = start_scheduler()
    yield
    if _scheduler_handle is not None:
        from app.scheduler import stop_scheduler

        stop_scheduler()


app = FastAPI(title="KOM Hunter", lifespan=lifespan)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class AddSegmentRequest(BaseModel):
    url: str


class SettingsUpdate(BaseModel):
    strava_client_id: str | None = None
    strava_client_secret: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None


class LoginRequest(BaseModel):
    password: str


# ---- login (gates /settings and its API) --------------------------------


@app.post("/api/login")
def login(body: LoginRequest, response: Response):
    try:
        ok = auth.check_password(body.password)
    except auth.AuthNotConfigured:
        raise HTTPException(
            status_code=503,
            detail="ADMIN_PASSWORD isn't set on the server. Add it in Vercel's Environment Variables first.",
        )
    if not ok:
        raise HTTPException(status_code=401, detail="Wrong password.")
    response.set_cookie(
        auth.COOKIE_NAME,
        auth.make_cookie_value(),
        max_age=60 * 60 * 24 * 180,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return {"ok": True}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"ok": True}


# ---- segments ----------------------------------------------------------


@app.get("/api/segments")
def list_segments(db: Session = Depends(get_db)):
    rows = db.execute(select(Segment).order_by(Segment.created_at.desc())).scalars().all()
    return [segments.segment_summary(s) for s in rows]


@app.post("/api/segments")
def create_segment(body: AddSegmentRequest, db: Session = Depends(get_db)):
    try:
        segment = segments.add_segment(db, body.url)
    except StravaError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return segments.segment_summary(segment)


@app.delete("/api/segments/{segment_id}")
def delete_segment(segment_id: int, db: Session = Depends(get_db)):
    segment = db.get(Segment, segment_id)
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")
    db.delete(segment)
    db.commit()
    return {"ok": True}


@app.post("/api/segments/{segment_id}/toggle")
def toggle_segment(segment_id: int, db: Session = Depends(get_db)):
    segment = db.get(Segment, segment_id)
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")
    segment.active = not segment.active
    db.commit()
    return segments.segment_summary(segment)


@app.get("/api/segments/{segment_id}/forecast")
def segment_forecast(segment_id: int, db: Session = Depends(get_db)):
    segment = db.get(Segment, segment_id)
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")

    mid_lat = (segment.start_lat + segment.end_lat) / 2
    mid_lng = (segment.start_lng + segment.end_lng) / 2

    try:
        forecast = weather.get_forecast(mid_lat, mid_lng, FORECAST_DAYS)
        baseline = weather.get_historical_baseline(mid_lat, mid_lng)
    except WeatherError as e:
        raise HTTPException(status_code=502, detail=str(e))

    windows = analysis.find_peak_windows(
        forecast=forecast,
        baseline=baseline,
        bearing_deg=segment.bearing_deg,
        wind_sensitivity=segment.wind_sensitivity,
    )
    return {
        "segment": segments.segment_summary(segment),
        "peak_windows": [w.__dict__ for w in windows],
    }


@app.post("/api/segments/{segment_id}/check")
def run_check_now(segment_id: int, db: Session = Depends(get_db)):
    segment = db.get(Segment, segment_id)
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")
    new_alerts = checker.check_segment(db, segment)
    return {"new_alerts_sent": len(new_alerts), "windows": [w.__dict__ for w in new_alerts]}


# ---- settings / connecting Strava & Telegram ---------------------------


def _settings_status(db: Session, s: AppSettings) -> dict:
    return {
        "strava_client_id": s.strava_client_id or "",
        "strava_has_secret": bool(s.strava_client_secret),
        "strava_connected": bool(s.strava_refresh_token),
        "telegram_bot_token": s.telegram_bot_token or "",
        "telegram_chat_id": s.telegram_chat_id or "",
        "telegram_connected": bool(s.telegram_bot_token and s.telegram_chat_id),
    }


@app.get("/api/settings")
def read_settings(db: Session = Depends(get_db), _auth: None = Depends(auth.require_auth)):
    return _settings_status(db, get_settings(db))


@app.post("/api/settings")
def update_settings(
    body: SettingsUpdate, db: Session = Depends(get_db), _auth: None = Depends(auth.require_auth)
):
    s = get_settings(db)
    if body.strava_client_id is not None:
        s.strava_client_id = body.strava_client_id.strip() or None
    if body.strava_client_secret is not None:
        s.strava_client_secret = body.strava_client_secret.strip() or None
    if body.telegram_bot_token is not None:
        s.telegram_bot_token = body.telegram_bot_token.strip() or None
    if body.telegram_chat_id is not None:
        s.telegram_chat_id = body.telegram_chat_id.strip() or None
    db.commit()
    return _settings_status(db, s)


@app.get("/auth/strava/start")
def strava_auth_start(request: Request, db: Session = Depends(get_db), _auth: None = Depends(auth.require_auth)):
    redirect_uri = str(request.base_url).rstrip("/") + "/auth/strava/callback"
    try:
        url = strava.build_authorize_url(db, redirect_uri)
    except StravaError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(url)


@app.get("/auth/strava/callback")
def strava_auth_callback(
    request: Request, db: Session = Depends(get_db), _auth: None = Depends(auth.require_auth)
):
    error = request.query_params.get("error")
    if error:
        return RedirectResponse(f"/settings?strava_error={error}")

    code = request.query_params.get("code")
    if not code:
        return RedirectResponse("/settings?strava_error=missing_code")

    try:
        strava.exchange_code_for_tokens(db, code)
    except StravaError as e:
        return RedirectResponse(f"/settings?strava_error={e}")
    return RedirectResponse("/settings?strava_connected=1")


@app.get("/api/telegram/chats")
def telegram_chats(db: Session = Depends(get_db), _auth: None = Depends(auth.require_auth)):
    s = get_settings(db)
    if not s.telegram_bot_token:
        raise HTTPException(status_code=400, detail="Save your Telegram bot token first.")
    try:
        chats = telegram.list_recent_chats(s.telegram_bot_token)
    except telegram.TelegramError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not chats:
        raise HTTPException(
            status_code=404,
            detail="No messages found yet. Send your bot any message on Telegram, then tap refresh again.",
        )
    return chats


@app.post("/api/telegram/test")
def telegram_test(db: Session = Depends(get_db), _auth: None = Depends(auth.require_auth)):
    try:
        telegram.send_message(db, "✅ KOM Hunter is connected. You'll hear from me when a peak tailwind shows up.")
    except telegram.TelegramError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


# ---- cron (Vercel Cron calls this on a schedule) ------------------------


@app.get("/api/cron/check-segments")
def cron_check_segments(request: Request, db: Session = Depends(get_db)):
    if CRON_SECRET:
        auth_header = request.headers.get("authorization", "")
        if auth_header != f"Bearer {CRON_SECRET}":
            raise HTTPException(status_code=401, detail="Unauthorized")

    results = checker.check_all_segments(db)
    return {
        "segments_checked": len(results),
        "alerts_sent": sum(len(w) for w in results.values()),
    }


# ---- static pages --------------------------------------------------------

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/settings")
def settings_page(request: Request):
    if not auth.is_authenticated(request):
        return RedirectResponse("/login")
    return FileResponse(STATIC_DIR / "settings.html")


@app.get("/login")
def login_page():
    return FileResponse(STATIC_DIR / "login.html")
