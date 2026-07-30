import requests
from sqlalchemy.orm import Session

from app.db import get_settings


class TelegramError(RuntimeError):
    pass


def is_connected(db: Session) -> bool:
    s = get_settings(db)
    return bool(s.telegram_bot_token and s.telegram_chat_id)


def send_message(db: Session, text: str) -> None:
    s = get_settings(db)
    if not (s.telegram_bot_token and s.telegram_chat_id):
        raise TelegramError("Telegram isn't connected yet. Go to /settings and connect it.")
    resp = requests.post(
        f"https://api.telegram.org/bot{s.telegram_bot_token}/sendMessage",
        json={
            "chat_id": s.telegram_chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise TelegramError(f"Telegram send failed: {resp.status_code} {resp.text}")


def list_recent_chats(bot_token: str) -> list[dict]:
    """Used by the /settings page to let the user pick their chat after
    messaging the bot once, instead of hunting for the chat id themselves."""
    resp = requests.get(f"https://api.telegram.org/bot{bot_token}/getUpdates", timeout=15)
    if resp.status_code != 200:
        raise TelegramError(f"Couldn't reach Telegram: {resp.status_code} {resp.text}")

    data = resp.json()
    if not data.get("ok"):
        raise TelegramError(f"Telegram rejected this bot token: {data.get('description', 'unknown error')}")

    seen = {}
    for update in data.get("result", []):
        msg = update.get("message") or update.get("channel_post")
        if not msg:
            continue
        chat = msg["chat"]
        name = chat.get("username") or chat.get("title") or chat.get("first_name") or "unknown"
        seen[chat["id"]] = {"chat_id": str(chat["id"]), "type": chat["type"], "name": name}
    return list(seen.values())


def format_peak_alert(segment_name: str, segment_url: str, window) -> str:
    local_time = window.time.strftime("%a %b %d, %I:%M %p")
    lines = [
        f"🚴 *KOM weather alert: {segment_name}*",
        f"_{local_time}_",
        "",
        window.reason,
    ]
    if window.wind_gust_mph:
        lines.append(f"Gusts up to {window.wind_gust_mph:.0f} mph")
    if window.temperature_f is not None:
        lines.append(f"Temp {window.temperature_f:.0f}°F")
    if window.precipitation_probability is not None:
        lines.append(f"Rain chance {window.precipitation_probability:.0f}%")
    lines.append("")
    lines.append(f"[View segment]({segment_url})")
    return "\n".join(lines)
