import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import analysis, checker, segments, weather
from app.config import FORECAST_DAYS
from app.db import Segment, SessionLocal, init_db
from app.scheduler import start_scheduler, stop_scheduler
from app.strava import StravaError
from app.weather import WeatherError

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
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


STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
