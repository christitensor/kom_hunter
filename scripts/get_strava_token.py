"""One-off helper: run the Strava OAuth flow locally to get a refresh token.

1. Create an API app at https://www.strava.com/settings/api
   - Set "Authorization Callback Domain" to: localhost
2. Run:
     STRAVA_CLIENT_ID=xxxx STRAVA_CLIENT_SECRET=yyyy python scripts/get_strava_token.py
3. A URL is printed -- open it in a browser, log in, click Authorize.
   Your browser will redirect to localhost and this script will catch it.
4. Copy the printed STRAVA_REFRESH_TOKEN into your .env.
"""

import http.server
import os
import sys
import urllib.parse
import webbrowser

import requests

CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
PORT = 8721
REDIRECT_URI = f"http://localhost:{PORT}/exchange_token"

if not (CLIENT_ID and CLIENT_SECRET):
    print("Usage: STRAVA_CLIENT_ID=xxxx STRAVA_CLIENT_SECRET=yyyy python scripts/get_strava_token.py")
    sys.exit(1)

auth_url = "https://www.strava.com/oauth/authorize?" + urllib.parse.urlencode(
    {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": "read",
    }
)

captured_code = {}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        code = qs.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        if code:
            captured_code["code"] = code
            self.wfile.write(b"<h1>Got it. You can close this tab and return to the terminal.</h1>")
        else:
            self.wfile.write(b"<h1>No authorization code found in the callback.</h1>")

    def log_message(self, *args):
        pass  # keep stdout clean


print(f"Open this URL to authorize (or it should open automatically):\n\n{auth_url}\n")
try:
    webbrowser.open(auth_url)
except Exception:
    pass

server = http.server.HTTPServer(("localhost", PORT), Handler)
while "code" not in captured_code:
    server.handle_request()

resp = requests.post(
    "https://www.strava.com/oauth/token",
    data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": captured_code["code"],
        "grant_type": "authorization_code",
    },
    timeout=15,
)
resp.raise_for_status()
data = resp.json()

print("\nSuccess! Add these to your .env:\n")
print(f"STRAVA_CLIENT_ID={CLIENT_ID}")
print(f"STRAVA_CLIENT_SECRET={CLIENT_SECRET}")
print(f"STRAVA_REFRESH_TOKEN={data['refresh_token']}")
