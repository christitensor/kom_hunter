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

The whole setup -- connecting Strava, wiring up Telegram -- happens from the
`/settings` page in the running app, from any browser (phone included). You
only need three things done in the Vercel dashboard first:

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
6. Create a Strava API app at **strava.com/settings/api**. Set its
   "Authorization Callback Domain" to your Vercel domain (no `https://`, no
   trailing slash -- the settings page shows you the exact value). Paste the
   Client ID and Secret into the Strava card, hit Save, then **Connect to
   Strava** and authorize.
7. Message **@BotFather** on Telegram, `/newbot`, paste the token it gives
   you into the Telegram card, hit **Save token**. Send your new bot any
   message (e.g. "hi"), then hit **Find my chat** and pick yourself from the
   list. Use **Send test message** to confirm it reaches you.
8. Back on the home page, paste a Strava segment URL and hit Track.

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
relying on Vercel Cron. Everything else -- connecting Strava and Telegram --
still happens at `http://localhost:8000/settings`.

## Project layout

```
api/index.py      Vercel entrypoint (re-exports the FastAPI app)
vercel.json       Cron schedule, function config
app/
  main.py          FastAPI app: segment CRUD, /settings API, OAuth callback, cron endpoint, login
  auth.py          Cookie gate for /settings and its API
  segments.py       Add-segment flow: parse URL -> fetch from Strava -> geometry -> save
  strava.py         OAuth authorize/callback + token refresh + segment fetch (DB-backed creds)
  weather.py        Open-Meteo forecast + historical baseline client
  wind.py           Bearing/tailwind/crosswind math, wind-sensitivity heuristic
  analysis.py       Peak-window scoring against the local baseline, ride-window filtering
  telegram.py       Alert formatting, sendMessage, chat discovery (DB-backed creds)
  checker.py        Ties it together per segment; dedupes via the notifications table
  scheduler.py      APScheduler background loop (self-hosted only; unused on Vercel)
  db.py             SQLAlchemy models: Segment, Notification, AppSettings
static/
  index.html         Segment list + add form
  settings.html      Connect Strava / Telegram from the browser (password-gated)
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
