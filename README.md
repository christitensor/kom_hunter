# KOM Hunter

Add a segment (paste a Strava link for a head start, or just fill in the
form), and KOM Hunter figures out which wind direction would give you the
biggest push on it, then watches the forecast for it. When conditions are a
genuine outlier for that spot -- not just "a bit breezy" -- it pings you on
Telegram so you can go time your attempt.

Track as many segments as you want at once, grouped by city with
notifications you can flip on or off for a whole area at a time.

No Strava account or API app is required. Strava only shares a segment's
exact route (the polyline) with a logged-in session, so rather than
impersonate one, segments are added with two coordinates you read straight
off any map -- the "Add segment" form has a click-to-pin map for that.
Pasting a Strava link and hitting **Autofill** still saves typing for the
rest (name, distance, grade, elevation, place) by reading Strava's public,
no-login embed widget for that segment -- no API key, OAuth, or connected
account involved.

## How it decides what's "peak"

1. **Segment geometry.** Computed from the start/end coordinates you give it
   (auto-filled from the map if you use it) -- distance, and the
   distance-weighted dominant direction of travel. That gives the ideal
   wind-FROM direction for a pure tailwind.
2. **Wind sensitivity.** A heuristic 0-1 score from grade and length: flat,
   long segments are aero/wind dominated; steep, short climbs are
   gravity-dominated and care less about wind. This scales the alert's
   framing, not just a hard on/off.
3. **Ride window.** Both the forecast candidates and the "typical wind"
   baseline itself are restricted to a local-time ride window -- only hours
   you can actually go ride matter, and "typical" means typical for that
   kind of ride, not diluted by hours that were never going to factor into
   an attempt anyway. Weekdays and weekends use separate windows, set via
   env vars: `RIDE_WINDOW_START_HOUR`/`RIDE_WINDOW_END_HOUR` (default
   4pm-8pm, Mon-Fri) and `WEEKEND_RIDE_WINDOW_START_HOUR`/
   `WEEKEND_RIDE_WINDOW_END_HOUR` (default 8am-8pm, Sat-Sun).
4. **Local baseline.** Pulls ~60 days of actual historical wind for the
   segment's location (Open-Meteo Archive API, ride-window hours only) and
   computes the mean/stdev of the tailwind component there.
5. **Peak detection.** A forecast hour only qualifies if *all* of:
   - Falls within the ride window above.
   - Tailwind component >= 10 mph **and** >= 1.25 standard deviations above
     that location's own typical wind (so "peak" is relative to the spot,
     not a global constant, and a merely typical or light breeze never
     qualifies).
   - Sustained wind <= 28 mph and gusts <= 38 mph (a gale is not a "good"
     KOM day even if the tailwind number is big -- it's just unrideable).
   - Rain chance <= 30% (wet pavement erases any aero gain).
6. Only the single best qualifying hour per day per segment gets alerted,
   and each forecast timestamp is only ever alerted once (deduped in the
   database), so you get a heads-up, not a flood.

This is a physically-reasoned heuristic, not a full aero/power simulation --
it doesn't know your CdA, weight, or power curve. It answers "is the wind
about to swing to your advantage in a way that's actually unusual and
actually safe/dry," which is the useful trigger for going and hunting a KOM.

## Deploying (Vercel, no CLI needed)

The whole setup -- wiring up Telegram -- happens from the `/settings` page in
the running app, from any browser (phone included). You only need three
things done in the Vercel dashboard first:

1. Deploy this project to Vercel (as a new project).
2. In the project's **Storage** tab, add a **Postgres** database (the Neon
   integration) and connect it -- this replaces local SQLite, since
   serverless functions don't keep a persistent disk. Free tier is enough.
3. In **Settings -> Environment Variables**, add `CRON_SECRET` set to any
   random string, then redeploy. This is what the scheduled weather check
   authenticates with; Vercel automatically sends it back as the `Cron`
   job's Authorization header, so the app just has to check it matches.
4. In the same Environment Variables page, add `ADMIN_PASSWORD` set to a
   password of your choosing, then redeploy. This gates `/settings` and its
   API -- **required if you plan to share the app's main URL with anyone**,
   since without it set, `/settings` refuses all access rather than
   silently allowing it (fail closed).

Then, in the deployed site itself:

5. Open `https://<your-project>.vercel.app/settings` and log in with the
   `ADMIN_PASSWORD` you set.
6. Message **@BotFather** on Telegram, `/newbot`, paste the token it gives
   you into the Telegram card, hit **Save token**. Send your new bot any
   message (e.g. "hi"), then hit **Find my chat** and pick yourself from the
   list. Use **Send test message** to confirm it reaches you.
7. Back on the home page, tap **+ Add segment**, optionally paste a Strava
   segment URL and hit **Autofill**, then drop the start/end pins on the map
   (or type coordinates) and hit **Track**.

Connecting a Strava API app in `/settings` is still there but entirely
optional now -- nothing in the add-segment or notification flow needs it.

The home page (segment list, forecasts) has no login and is safe to share --
it doesn't expose any credentials. Only `/settings` and its API are gated.

A Vercel Cron Job hits `/api/cron/check-segments` once a day (`vercel.json`,
`0 14 * * *` = 2pm UTC by default -- change the hour to whenever you want it
to run) and Telegrams you when a tracked segment's forecast shows a peak
tailwind window in the next `FORECAST_DAYS` (7 by default).

> Vercel's Hobby (free) plan restricts Cron Jobs to once a day -- that's
> what `vercel.json` is set to. Upgrade to Pro if you want it checking
> more often than daily.

## Running it yourself instead (VPS, Railway, home server, etc.)

The same codebase runs as a normal always-on process -- no Vercel-specific
pieces required:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Without a `DATABASE_URL` env var it falls back to a local SQLite file, and
without `VERCEL` set it starts an in-process APScheduler loop instead of
relying on Vercel Cron. Everything else -- wiring up Telegram --
still happens at `http://localhost:8000/settings`.

## Project layout

```
api/index.py      Vercel entrypoint (re-exports the FastAPI app)
vercel.json       Cron schedule, function config
app/
  main.py          FastAPI app: segment CRUD, city notification toggle, /settings API, OAuth callback, cron endpoint, login
  auth.py          Cookie gate for /settings and its API
  segments.py       Manual add-segment flow: validate input -> geometry -> save; per-segment summary
  geo.py            Strava-API-free lookups: public embed-widget scrape for autofill, Open-Meteo/Nominatim geocoding
  strava.py         OAuth authorize/callback + token refresh (DB-backed creds; optional, unused by add-segment)
  weather.py        Open-Meteo forecast + historical baseline client
  wind.py           Bearing/tailwind/crosswind math, wind-sensitivity heuristic
  analysis.py       Peak-window scoring against the local baseline, ride-window filtering
  telegram.py       Alert formatting, sendMessage, chat discovery (DB-backed creds)
  checker.py        Ties it together per segment; dedupes via the notifications table
  scheduler.py      APScheduler background loop (self-hosted only; unused on Vercel)
  db.py             SQLAlchemy models: Segment (incl. city), Notification, AppSettings
static/
  index.html         Segment list grouped by city (collapsible, per-city notification toggle) + add-segment form with pin map
  settings.html      Connect Telegram (and, optionally, Strava) from the browser (password-gated)
  login.html         Password form for /settings
  favicon.ico, favicon.svg, apple-touch-icon.png, icon-192.png, icon-512.png, manifest.webmanifest
                      App icon (a crown, in Strava's brand orange) + PWA manifest
scripts/
  gen_icons.py       Regenerates the icon files above (run locally with Pillow; not a runtime dep)
tests/              pytest unit tests for the wind math and peak-detection logic
```

## Tests

```bash
pip install -r requirements.txt pytest httpx
pytest
```
