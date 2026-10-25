"""/ai in the Telegram bot: how much of the free AI allowance is used and when it comes back.

OpenRouter's free tier allows `openrouter_daily_limit` (50) calls a day per ACCOUNT (reset 00:00 UTC = 08:00 Kuala Lumpur). The counters live in
logs/ai_budget.json (app/services/ai_budget.py), one file per machine, so this server's count is only its own share when the same key is also
used by a local dev copy; the real limit message from OpenRouter (blocked_until) is what is shared. The hourly counter is the web server
process's own."""

import html
import logging
from datetime import datetime, timezone

import requests

from app.core.config import settings
from app.services import ai_budget

log = logging.getLogger(__name__)


def _hm(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, minutes = divmod(seconds // 60, 60)
    return f"{hours} h {minutes} min" if hours else f"{minutes} min"


def account_info() -> dict | None:
    """OpenRouter's own view of this key (GET /api/v1/key): credits used / limit and whether it is a free-tier account. None on any problem."""
    if not settings.openrouter_api_key:
        return None
    try:
        r = requests.get("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {settings.openrouter_api_key}"}, timeout=8)
        r.raise_for_status()
        return r.json().get("data") or None
    except (requests.RequestException, ValueError):
        log.info("OpenRouter key info could not be read")  # never log the key or the URL with headers
        return None


def build_message(now: datetime | None = None, account: dict | None = None) -> str:
    from app.services.telegram_digest_service import TZ

    now = now or datetime.now(timezone.utc)
    usage = ai_budget.usage(now.timestamp())
    limit = usage["daily_limit"]
    lines = [f"🤖 <b>AI usage</b> · {now.astimezone(TZ).strftime('%d %b %H:%M')} (KL)"]
    if usage["blocked"]:
        back = datetime.fromtimestamp(usage["blocked_until"], TZ).strftime("%d %b %H:%M")
        lines += [f"🔴 <b>Free AI limit reached.</b> No AI summaries until {back} (KL), in {_hm(usage['blocked_until'] - now.timestamp())}.", ""]
    elif limit and usage["used"] >= limit:
        lines += ["🔴 <b>This server has used all of today's calls.</b>", ""]
    elif limit and usage["left_for_visits"] <= 5:
        lines += ["🟠 <b>Almost used up for today.</b>", ""]
    else:
        lines += ["🟢 <b>Available.</b>", ""]
    if limit:
        filled = min(10, round(10 * usage["used"] / limit))
        if usage["blocked"]:
            lines.append(f"Counted by this server today: <b>{usage['used']} of {limit}</b> calls. OpenRouter says the account's limit is already reached, so the rest was spent by another copy of the site on the same key (for example your local test site).")
        else:
            lines.append(f"Today (resets 08:00 KL): <b>{usage['used']} of {limit}</b> calls used, <b>{usage['left_for_visits']}</b> left for page visits")
        lines.append("▰" * filled + "▱" * (10 - filled))
        lines.append(f"Background jobs (Telegram post sorting, news targeting) stop at {usage['background_stops_at']} used so {usage['visit_reserve']} calls stay for AI summaries when someone opens a page.")
    else:
        lines.append(f"Today: <b>{usage['used']}</b> calls used (no daily limit set).")
    if usage["hourly_cap"]:
        lines.append(f"This hour (web server): {usage['calls_last_hour']} of {usage['hourly_cap']} calls")
    info = account if account is not None else account_info()
    if info:
        tier = "free tier" if info.get("is_free_tier") else "paid account"
        credit = f", credits used ${float(info.get('usage') or 0):.2f}" + (f" of ${float(info['limit']):.2f}" if info.get("limit") else "")
        lines.append(f"OpenRouter key: {html.escape(tier)}{credit}")
    lines += [
        "",
        "ℹ️ The limit belongs to the OpenRouter account, so every copy of the site that uses the same key (live and your local test site) spends from the same 50 a day; this count is only what this server made.",
        "Malay translation uses the local model: no AI calls, no limit.",
    ]
    return "\n".join(lines)
