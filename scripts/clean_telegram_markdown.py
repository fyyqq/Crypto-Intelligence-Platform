"""One-time historical cleanup: strips literal Markdown syntax out of
already-stored Telegram rows' title/full_body_text.

Root cause (fixed going forward in app/services/telegram_pipeline.py):
every row ingested before this fix used Telethon's `message.text`, which
re-serializes the message's real formatting entities (bold, italic, code,
links) back into literal Markdown characters — e.g. a real bold run
became the literal text "**bold**" — rather than `message.raw_text`
(plain text, entities simply dropped, no syntax at all). Since /news's
cards render plain text, not Markdown, this showed up as literal
asterisks/underscores/backticks/link-brackets on the page.

This is a pure Postgres read+update — no Telethon/live Telegram session
involved at all, so it's safe to run even while the pipeline's own
Telethon session is in use elsewhere (no "database is locked"/session-
conflict risk the way two concurrent `telegram_pipeline.py` runs would have).

Usage:
    source .venv/bin/activate
    python scripts/clean_telegram_markdown.py
"""

import os
import re

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DSN = os.environ.get(
    "NEWS_DATABASE_DSN",
    "dbname=crypto_intelligence user=crypto password=crypto host=localhost port=5432",
)

# Markdown-style link "[label](url)" -> "label" — the post's own real
# permalink is already shown separately by the card, so the URL half of
# the link is just dropped, not preserved anywhere else.
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_ITALIC_RE = re.compile(r"__(.+?)__", re.DOTALL)
_STRIKE_RE = re.compile(r"~~(.+?)~~", re.DOTALL)
_CODE_BLOCK_RE = re.compile(r"```(.+?)```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]+?)`")
# Catches any marker left over from a truncated/unbalanced pair (e.g. a
# title cut off at 200 chars mid-bold-run, leaving one trailing "**" with
# no matching close) that the paired patterns above couldn't match.
_STRAY_MARKERS_RE = re.compile(r"\*\*|__|~~|```|`")


def clean(text: str | None) -> str | None:
    if not text:
        return text
    cleaned = _LINK_RE.sub(r"\1", text)
    cleaned = _BOLD_RE.sub(r"\1", cleaned)
    cleaned = _ITALIC_RE.sub(r"\1", cleaned)
    cleaned = _STRIKE_RE.sub(r"\1", cleaned)
    cleaned = _CODE_BLOCK_RE.sub(r"\1", cleaned)
    cleaned = _INLINE_CODE_RE.sub(r"\1", cleaned)
    cleaned = _STRAY_MARKERS_RE.sub("", cleaned)
    return cleaned


def main() -> None:
    conn = psycopg2.connect(DSN)
    cur = conn.cursor()
    cur.execute("SELECT id, title, full_body_text FROM news_articles WHERE source_type = 'telegram'")
    rows = cur.fetchall()

    updated = 0
    for row_id, title, body in rows:
        new_title = clean(title)
        new_body = clean(body)
        if new_title != title or new_body != body:
            cur.execute(
                "UPDATE news_articles SET title = %s, full_body_text = %s WHERE id = %s",
                (new_title, new_body, row_id),
            )
            updated += 1
    conn.commit()
    cur.close()
    conn.close()

    print(f"Checked {len(rows)} Telegram rows — cleaned {updated} with literal Markdown syntax.")


if __name__ == "__main__":
    main()
