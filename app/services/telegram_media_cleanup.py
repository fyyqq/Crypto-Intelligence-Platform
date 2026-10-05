"""Keeps frontend/assets/telegram_media/ from growing without bound.

Three jobs, each safe to re-run (idempotent — a clean pass just finds
nothing to do):

1. ``convert_legacy_images_to_webp`` — one-time backfill for files saved
   before telegram_pipeline.py started saving .webp directly: converts any
   remaining .jpg/.jpeg/.png post photo or video poster, rewrites every
   news_articles row that references it, then deletes the original.
2. ``strip_existing_videos`` — one-time backfill for posts stored before
   videos stopped being downloaded: deletes the playable video file and
   clears its row's ``src`` (keeping the already-downloaded poster image),
   so the post falls back to "poster + Watch on Telegram" — the same
   display an over-size video already used.
3. ``prune_old_media`` — ongoing: Telegram posts older than
   MEDIA_RETENTION_DAYS have their remaining image files deleted and
   image_url/media cleared, so the app's own existing fallback (category
   image, or the group's avatar) takes over automatically
   (frontend/state/news_state.py::_fallback_image_for /
   _telegram_group_avatar). Article TEXT (title, body, summaries) is never
   touched by any of these — only image_url/media.

Group avatar files (_avatar_<username>.*) are never touched: they're never
referenced by image_url/media (frontend resolves them purely by filename
pattern), so they're never a candidate for deletion here by construction.

Pure filesystem + Postgres work — no Telegram/Telethon session needed, so
this is safe to run alongside the live listener.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import text

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_TELEGRAM_MEDIA_DIR = _REPO_ROOT / "frontend" / "assets" / "telegram_media"
MEDIA_RETENTION_DAYS = 30


def _session():
    from app.core.database import SessionLocal

    return SessionLocal()


def _path_for(src: str) -> Path | None:
    """The real file a stored "/telegram_media/<name>" URL points at, or
    None if it's not that kind of path (e.g. empty, or an external URL)."""
    if not src or not src.startswith("/telegram_media/"):
        return None
    return _TELEGRAM_MEDIA_DIR / src[len("/telegram_media/") :]


def _safe_unlink(path: Path) -> int:
    """Deletes a file if it exists and is really inside telegram_media/
    (defence against a malformed path escaping the directory). Returns the
    bytes freed, 0 if nothing was deleted."""
    try:
        path = path.resolve()
        if _TELEGRAM_MEDIA_DIR.resolve() not in path.parents:
            return 0
        if not path.is_file():
            return 0
        size = path.stat().st_size
        path.unlink()
        return size
    except OSError as exc:
        logger.warning("Could not delete %s: %s", path, exc)
        return 0


# ---------------------------------------------------------------------------
# 1. One-time backfill: legacy jpg/png -> webp
# ---------------------------------------------------------------------------
def convert_legacy_images_to_webp() -> dict:
    from PIL import Image

    candidates = [
        p
        for p in _TELEGRAM_MEDIA_DIR.glob("*")
        if p.is_file()
        and p.suffix.lower() in (".jpg", ".jpeg", ".png")
        and not p.name.startswith("_avatar_")
    ]
    if not candidates:
        return {"converted": 0, "bytes_saved": 0}

    renamed: dict[str, str] = {}  # "/telegram_media/old.jpg" -> ".../new.webp"
    bytes_before = bytes_after = 0
    for path in candidates:
        try:
            old_size = path.stat().st_size
            webp_path = path.with_suffix(".webp")
            if webp_path.exists():
                continue  # already converted in a prior partial run
            with Image.open(path) as img:
                img.convert("RGB").save(webp_path, "WEBP", quality=80)
            renamed[f"/telegram_media/{path.name}"] = f"/telegram_media/{webp_path.name}"
            bytes_before += old_size
            bytes_after += webp_path.stat().st_size
        except Exception as exc:  # noqa: BLE001 — one bad file must not stop the batch
            logger.warning("SKIP webp backfill for %s: %s", path.name, exc)

    if not renamed:
        return {"converted": 0, "bytes_saved": 0}

    db = _session()
    try:
        rows = db.execute(
            text(
                "SELECT id, image_url, media FROM news_articles "
                "WHERE source_type = 'telegram' AND (image_url IS NOT NULL OR media IS NOT NULL)"
            )
        ).all()
        for row_id, image_url, media in rows:
            changed = False
            if image_url in renamed:
                image_url = renamed[image_url]
                changed = True
            if media:
                new_media = []
                for item in media:
                    item = dict(item)
                    if item.get("src") in renamed:
                        item["src"] = renamed[item["src"]]
                        changed = True
                    if item.get("poster") in renamed:
                        item["poster"] = renamed[item["poster"]]
                        changed = True
                    new_media.append(item)
                media = new_media
            if changed:
                db.execute(
                    text("UPDATE news_articles SET image_url = :image_url, media = :media WHERE id = :id"),
                    {"image_url": image_url, "media": json.dumps(media) if media is not None else None, "id": row_id},
                )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    # Only remove the originals once every referencing row has been repointed.
    for old_url in renamed:
        _safe_unlink(_TELEGRAM_MEDIA_DIR / old_url[len("/telegram_media/") :])

    return {"converted": len(renamed), "bytes_saved": max(0, bytes_before - bytes_after)}


# ---------------------------------------------------------------------------
# 2. One-time backfill: strip playable video files, keep the poster
# ---------------------------------------------------------------------------
def strip_existing_videos() -> dict:
    db = _session()
    freed = 0
    stripped = 0
    try:
        rows = db.execute(
            text(
                "SELECT id, media FROM news_articles "
                "WHERE source_type = 'telegram' AND media::text LIKE '%\"type\": \"video\"%'"
            )
        ).all()
        for row_id, media in rows:
            if not media:
                continue
            changed = False
            new_media = []
            for item in media:
                item = dict(item)
                if item.get("type") == "video" and item.get("src"):
                    path = _path_for(item["src"])
                    if path is not None:
                        freed += _safe_unlink(path)
                    item["src"] = ""
                    changed = True
                    stripped += 1
                new_media.append(item)
            if changed:
                db.execute(
                    text("UPDATE news_articles SET media = :media WHERE id = :id"),
                    {"media": json.dumps(new_media), "id": row_id},
                )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return {"videos_stripped": stripped, "bytes_saved": freed}


# ---------------------------------------------------------------------------
# 3. Ongoing: prune media for posts older than MEDIA_RETENTION_DAYS
# ---------------------------------------------------------------------------
def prune_old_media(days: int = MEDIA_RETENTION_DAYS, now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=days)
    db = _session()
    freed = 0
    pruned = 0
    try:
        rows = db.execute(
            text(
                "SELECT id, image_url, media FROM news_articles "
                "WHERE source_type = 'telegram' AND published_date < :cutoff "
                "AND (image_url IS NOT NULL OR (media IS NOT NULL AND media::text != '[]'))"
            ),
            {"cutoff": cutoff},
        ).all()
        if not rows:
            return {"pruned": 0, "bytes_saved": 0}

        # Files still needed by a post that is NOT expiring (same filename
        # could in principle be referenced elsewhere) are never deleted.
        still_needed: set[str] = set()
        for (image_url, media) in db.execute(
            text(
                "SELECT image_url, media FROM news_articles "
                "WHERE source_type = 'telegram' AND published_date >= :cutoff"
            ),
            {"cutoff": cutoff},
        ).all():
            if image_url:
                still_needed.add(image_url)
            for item in media or []:
                if item.get("src"):
                    still_needed.add(item["src"])
                if item.get("poster"):
                    still_needed.add(item["poster"])

        for row_id, image_url, media in rows:
            urls = set()
            if image_url:
                urls.add(image_url)
            for item in media or []:
                if item.get("src"):
                    urls.add(item["src"])
                if item.get("poster"):
                    urls.add(item["poster"])
            for url in urls - still_needed:
                path = _path_for(url)
                if path is not None:
                    freed += _safe_unlink(path)
            db.execute(
                text("UPDATE news_articles SET image_url = NULL, media = '[]'::jsonb WHERE id = :id"),
                {"id": row_id},
            )
            pruned += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return {"pruned": pruned, "bytes_saved": freed}


def run_media_maintenance() -> dict:
    """Everything this module does, in the right order. Called once at
    startup and periodically after that (frontend/news_catchup.py); steps 1
    and 2 are no-ops once their one-time backfill is done."""
    results = {
        "webp": convert_legacy_images_to_webp(),
        "videos": strip_existing_videos(),
        "pruned": prune_old_media(),
    }
    logger.info("telegram media maintenance: %s", results)
    return results
