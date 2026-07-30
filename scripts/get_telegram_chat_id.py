"""One-off helper: find your Telegram chat_id for KOM Hunter alerts.

1. Create a bot with @BotFather on Telegram, grab its token.
2. Send that bot any message (e.g. "hi").
3. Run:  TELEGRAM_BOT_TOKEN=xxxx python scripts/get_telegram_chat_id.py
4. Copy the printed chat_id into your .env as TELEGRAM_CHAT_ID.
"""

import os
import sys

import requests

token = os.getenv("TELEGRAM_BOT_TOKEN") or (sys.argv[1] if len(sys.argv) > 1 else None)
if not token:
    print("Usage: TELEGRAM_BOT_TOKEN=xxxx python scripts/get_telegram_chat_id.py")
    sys.exit(1)

resp = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=15)
resp.raise_for_status()
data = resp.json()

results = data.get("result", [])
if not results:
    print("No messages found yet. Send your bot a message on Telegram, then re-run this script.")
    sys.exit(1)

seen = set()
for update in results:
    msg = update.get("message") or update.get("channel_post")
    if not msg:
        continue
    chat = msg["chat"]
    key = chat["id"]
    if key in seen:
        continue
    seen.add(key)
    name = chat.get("username") or chat.get("title") or chat.get("first_name") or "unknown"
    print(f"chat_id={chat['id']}  ({chat['type']}, {name})")
