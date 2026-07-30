import requests

from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


class TelegramError(RuntimeError):
    pass


def send_message(text: str) -> None:
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        raise TelegramError(
            "Telegram is not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID "
            "(see scripts/get_telegram_chat_id.py)."
        )
    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise TelegramError(f"Telegram send failed: {resp.status_code} {resp.text}")


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
