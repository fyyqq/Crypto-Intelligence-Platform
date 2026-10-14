"""/site_health: one message on whether the site's data pipelines are alive.

Each check returns (level, text) with level "ok" | "warn" | "bad"; a check that
itself fails is reported as bad rather than hiding the others. The command runs
inside the Reflex process of the server that owns the bot (live), so the
in-process checks (exchange prices, alert watcher) describe that server."""
import html
import logging
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.price_alert import PriceAlert
from app.models.price_snapshot import PriceSnapshot
from app.models.sync_log import SyncLog, SyncStatus, SyncType
from app.services import heartbeat

log = logging.getLogger(__name__)
DOT = {"ok": "🟢", "warn": "🟠", "bad": "🔴"}


def _ago(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 90:
        return f"{s}s ago"
    if s < 5400:
        return f"{s // 60} min ago"
    if s < 172800:
        return f"{s / 3600:.1f} h ago".replace(".0 ", " ")
    return f"{s // 86400} days ago"


def _age_level(seconds: float, warn: float, bad: float) -> str:
    return "ok" if seconds <= warn else "warn" if seconds <= bad else "bad"


def _since(naive_utc: datetime) -> float:
    return (datetime.now(timezone.utc).replace(tzinfo=None) - naive_utc).total_seconds()


def check_database() -> tuple[str, str]:
    import time

    t = time.perf_counter()
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    finally:
        db.close()
    ms = (time.perf_counter() - t) * 1000
    return ("ok" if ms < 500 else "warn"), f"Database: reachable, {ms:.0f} ms"


def check_snapshots() -> tuple[str, str]:
    db = SessionLocal()
    try:
        latest = db.scalar(select(func.max(PriceSnapshot.synced_at)))
        n = db.scalar(select(func.count()).where(PriceSnapshot.synced_at == latest)) if latest else 0
    finally:
        db.close()
    if latest is None:
        return "bad", "Price snapshots (feed the Gainers & Losers boards): none stored"
    age = _since(latest)
    return _age_level(age, 75 * 60, 3 * 3600), f"Price snapshots: latest {_ago(age)}, {n} coins (hourly)"


def check_exchange_prices() -> tuple[str, str]:
    from app.services import price_hub

    price_hub.get_prices()  # refreshes when older than 30s, so this tests the exchanges for real
    st = price_hub.status()
    if st["age_seconds"] is None:
        return "warn", "Exchange prices (live price list): not loaded yet in this process"
    down = f", down: {', '.join(st['down'])}" if st["down"] else ""
    level = "bad" if not st["symbols"] else _age_level(st["age_seconds"], 120, 900)
    if level == "ok" and st["down"]:
        level = "warn"
    return level, f"Exchange prices: {st['symbols']} symbols, refreshed {_ago(st['age_seconds'])}{down}"


def check_cmc() -> tuple[str, str]:
    from app.services import cmc_budget

    db = SessionLocal()
    try:
        row = db.execute(
            select(SyncLog).where(SyncLog.sync_type == SyncType.LISTINGS_HOT).order_by(SyncLog.id.desc()).limit(1)
        ).scalar_one_or_none()
        ok = db.execute(
            select(SyncLog.finished_at).where(
                SyncLog.sync_type == SyncType.LISTINGS_HOT, SyncLog.status == SyncStatus.SUCCESS
            ).order_by(SyncLog.id.desc()).limit(1)
        ).scalar_one_or_none()
    finally:
        db.close()
    parts, level = [], "ok"
    u = cmc_budget.usage()
    if u is None:
        parts.append("credits unreadable")
        level = "warn"
    elif u["left"] <= 0:
        parts.append(f"credits USED UP ({u['used']:,}/{u['limit']:,}, resets {u['reset_at'][:10]})")
        level = "bad"
    else:
        parts.append(f"{u['left']:,} of {u['limit']:,} credits left")
        if u["left"] < 1500:
            level = "warn"
    if row is not None and row.status == SyncStatus.FAILED:
        parts.append(f"last hourly sync FAILED {_ago(_since(row.started_at))}" + (f" ({row.error_message.split(' for url')[0][:60]})" if row.error_message else ""))
        level = "bad" if level != "bad" else level
    elif ok is not None:
        age = _since(ok)
        parts.append(f"last good sync {_ago(age)}")
        if _age_level(age, 2 * 3600, 6 * 3600) != "ok":
            level = max(level, "warn", key=("ok", "warn", "bad").index)
    else:
        parts.append("no sync recorded")
        level = "warn"
    return level, "CoinMarketCap: " + "; ".join(parts)


def check_news() -> tuple[str, str]:
    db = SessionLocal()
    try:
        newest = dict(db.execute(text(
            "SELECT source_type, MAX(published_date) FROM news_articles WHERE source_type IN ('rss','telegram','google_news') GROUP BY 1"
        )).all())
        ok = db.execute(
            select(SyncLog.finished_at).where(SyncLog.sync_type == SyncType.NEWS_PIPELINE, SyncLog.status == SyncStatus.SUCCESS)
            .order_by(SyncLog.id.desc()).limit(1)
        ).scalar_one_or_none()
        running = db.execute(
            select(SyncLog.started_at).where(SyncLog.sync_type == SyncType.NEWS_PIPELINE, SyncLog.status == SyncStatus.RUNNING)
            .order_by(SyncLog.id.desc()).limit(1)
        ).scalar_one_or_none()
    finally:
        db.close()
    freshest = max((v for v in newest.values() if v), default=None)
    parts, level = [], "ok"
    if freshest is None:
        return "bad", "News: no articles"
    age = _since(freshest)
    parts.append(f"newest article {_ago(age)}")
    level = _age_level(age, 3 * 3600, 12 * 3600)
    if ok is not None:
        pa = _since(ok)
        parts.append(f"pipeline last ok {_ago(pa)}")
        lv = _age_level(pa, 3 * 3600, 8 * 3600)
        level = max(level, lv, key=("ok", "warn", "bad").index)
    if running is not None and _since(running) > 90 * 60:
        parts.append(f"a pipeline run has been 'running' for {_ago(_since(running)).replace(' ago', '')}")
        level = "bad"
    return level, "News: " + ", ".join(parts)


def check_telegram_listener() -> tuple[str, str]:
    found = subprocess.run(["pgrep", "-f", "app.services.telegram_listener"], capture_output=True).returncode == 0
    return ("ok", "News listener (Telegram groups): running") if found else ("bad", "News listener (Telegram groups): NOT running")


def check_alert_watcher() -> tuple[str, str]:
    db = SessionLocal()
    try:
        active = db.scalar(select(func.count()).select_from(PriceAlert).where(PriceAlert.triggered_at.is_(None))) or 0
    finally:
        db.close()
    age = heartbeat.age("alert_watcher")
    if age is None:
        return "bad", f"Price alerts: watcher has not run in this process ({active} active alerts)"
    return _age_level(age, 60, 300), f"Price alerts: watcher checked {_ago(age)}, {active} active"


def check_server() -> tuple[str, str]:
    parts, level = [], "ok"
    disk = shutil.disk_usage("/")
    free = disk.free / disk.total * 100
    parts.append(f"disk {free:.0f}% free")
    if free < 7:
        level = "bad"
    elif free < 15:
        level = "warn"
    load = os.getloadavg()[0] / (os.cpu_count() or 1)
    parts.append(f"load {load:.2f}/core")
    if load > 2:
        level = "warn" if level == "ok" else level
    try:
        mem = {k: int(v.split()[0]) for k, v in (l.split(":", 1) for l in open("/proc/meminfo").read().splitlines())}
        avail = mem["MemAvailable"] / mem["MemTotal"] * 100
        parts.append(f"memory {avail:.0f}% available")
        if avail < 5:
            level = "bad"
        elif avail < 12 and level == "ok":
            level = "warn"
    except OSError:
        pass  # not Linux (local dev)
    return level, "Server: " + ", ".join(parts)


def check_daily_messages() -> tuple[str, str]:
    from app.services import telegram_digest_service as dg

    if not settings.telegram_digest:
        return "ok", "Daily Telegram messages: off on this server"
    sent = dg._load_sent()
    now = datetime.now(dg.TZ)
    today = now.date().isoformat()
    missing = [i for i in dg.AUTO_ITEMS if sent.get(i) != today]
    if not missing or now.hour < dg.SEND_HOUR + 1:
        last = ", ".join(f"{i}: {sent.get(i, 'never')}" for i in dg.AUTO_ITEMS)
        return "ok", f"Daily Telegram messages (08:00 KL): last sent {last}"
    return "warn", f"Daily Telegram messages: not sent today yet: {', '.join(missing)}"


CHECKS = [
    check_database, check_snapshots, check_exchange_prices, check_cmc, check_news,
    check_telegram_listener, check_alert_watcher, check_server, check_daily_messages,
]


def run_checks() -> list[tuple[str, str]]:
    results = []
    for fn in CHECKS:
        try:
            results.append(fn())
        except Exception as exc:  # noqa: BLE001  (a broken check is itself a finding)
            log.exception("health check %s failed", fn.__name__)
            results.append(("bad", f"{fn.__name__.removeprefix('check_').replace('_', ' ').capitalize()}: check failed ({type(exc).__name__})"))
    return results


def build_message(results: list[tuple[str, str]] | None = None, now: datetime | None = None) -> str:
    from app.services.telegram_digest_service import TZ

    results = run_checks() if results is None else results
    bad = sum(1 for lv, _ in results if lv == "bad")
    warn = sum(1 for lv, _ in results if lv == "warn")
    if bad:
        summary = f"🔴 {bad} problem{'s' if bad > 1 else ''}" + (f", {warn} warning{'s' if warn > 1 else ''}" if warn else "")
    elif warn:
        summary = f"🟠 {warn} warning{'s' if warn > 1 else ''}"
    else:
        summary = "🟢 Everything looks normal"
    stamp = (now or datetime.now(TZ)).strftime("%d %b %H:%M")
    lines = [f"🩺 <b>Site health</b> · {stamp} (KL)", summary, ""]
    # problems first, then warnings, then the rest
    for lv, txt in sorted(results, key=lambda r: ("bad", "warn", "ok").index(r[0])):
        lines.append(f"{DOT[lv]} {html.escape(txt)}")
    return "\n".join(lines)
