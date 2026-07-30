# KOM Hunter

Paste a Strava segment link, and KOM Hunter figures out which wind direction
would give you the biggest push on that segment, then watches the forecast
for it. When conditions are a genuine outlier for that spot -- not just "a
bit breezy" -- it pings you on Telegram so you can go time your attempt.

Track as many segments as you want at once.

## How it decides what's "peak"

1. **Segment geometry.** Pulls the segment from the Strava API and computes
   its distance-weighted dominant direction of travel from the route
   polyline (not just start->end, so curvy segments are handled sensibly).
   That gives the ideal wind-FROM direction for a pure tailwind.
2. **Wind sensitivity.** A heuristic 0-1 score from grade and length: flat,
   long segments are aero/wind dominated; steep, short climbs are
   gravity-dominated and care less about wind. This scales the alert's
   framing, not just a hard on/off.
3. **Local baseline.** Pulls ~60 days of actual historical wind for the
   segment's location (Open-Meteo Archive API) and computes the mean/stdev
   of the tailwind component there.
4. **Peak detection.** A forecast hour only qualifies if *all* of:
   - Tailwind component >= 10 mph **and** >= 1.25 standard deviations above
     that location's own typical wind (so "peak" is relative to the spot,
     not a global constant, and a merely typical or light breeze never
     qualifies).
   - Sustained wind <= 28 mph and gusts <= 38 mph (a gale is not a "good"
     KOM day even if the tailwind number is big -- it's just unrideable).
   - Rain chance <= 30% (wet pavement erases any aero gain).
5. Only the single best qualifying hour per day per segment gets alerted,
   and each forecast timestamp is only ever alerted once (deduped in
   SQLite), so you get a heads-up, not a flood.

This is a physically-reasoned heuristic, not a full aero/power simulation --
it doesn't know your CdA, weight, or power curve. It answers "is the wind
about to swing to your advantage in a way that's actually unusual and
actually safe/dry," which is the useful trigger for going and hunting a KOM.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 1. Strava API credentials

1. Create an API app at https://www.strava.com/settings/api (Authorization
   Callback Domain: `localhost`). Note the Client ID and Client Secret.
2. Get a refresh token:
   ```bash
   STRAVA_CLIENT_ID=xxxx STRAVA_CLIENT_SECRET=yyyy python scripts/get_strava_token.py
   ```
   It opens a browser for you to authorize, then prints the three values to
   put in `.env`.

### 2. Telegram bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram, `/newbot`, copy
   the token into `.env` as `TELEGRAM_BOT_TOKEN`.
2. Send your new bot any message (e.g. "hi") so it can see your chat.
3. Run:
   ```bash
   TELEGRAM_BOT_TOKEN=xxxx python scripts/get_telegram_chat_id.py
   ```
   Copy the printed `chat_id` into `.env` as `TELEGRAM_CHAT_ID`.

### 3. Run it

```bash
uvicorn app.main:app --reload
```

Open http://localhost:8000, paste a segment URL (e.g.
`https://www.strava.com/segments/12345678`), click Track. The app polls
every `CHECK_INTERVAL_HOURS` (default 3) in the background and Telegrams you
when a peak window shows up in the next `FORECAST_DAYS` (default 7).

Each tracked segment card shows its current forecasted peak windows, and has
buttons to check it immediately, pause/resume, or stop tracking it.

## Project layout

```
app/
  main.py        FastAPI app: /api/segments CRUD, forecast preview, manual check
  segments.py     Add-segment flow: parse URL -> fetch from Strava -> geometry -> save
  strava.py       OAuth token refresh + segment fetch
  weather.py      Open-Meteo forecast + historical baseline client
  wind.py         Bearing/tailwind/crosswind math, wind-sensitivity heuristic
  analysis.py     Peak-window scoring against the local baseline
  telegram.py     Alert formatting + sendMessage
  checker.py      Ties it together per segment; dedupes via the notifications table
  scheduler.py    APScheduler background poll job
  db.py           SQLite models (Segment, Notification)
static/index.html Single-page UI
scripts/          One-off OAuth/chat-id helper scripts
tests/            pytest unit tests for the wind math and peak-detection logic
```

## Tests

```bash
pip install -r requirements.txt pytest httpx
pytest
```
