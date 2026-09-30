"""One-time backfill for the INTRADAY.my Telegram group.

Its posts are a short teaser plus a link to the article on intraday.my
(e.g. "Baca di sini 👉🏻 https://intraday.my/2026/<slug>/"). New posts get the
linked article's real body at ingestion (telegram_pipeline.expand_linked_article);
this script does the same for posts stored before that existed, and renames
the source from the group's long slogan to "INTRADAY.my".

Idempotent: it only touches posts whose body still contains the intraday.my
link, and the fetched article body doesn't, so a re-run only retries posts
whose fetch failed. The post's title (its first line) is left as it was.

No Telethon/Telegram session is used, so it's safe to run while the listener
is running.

Usage:
    source .venv/bin/activate
    python scripts/expand_intraday_links.py
"""

import time

import psycopg2

from app.services.telegram_pipeline import (
    _DISPLAY_NAME_OVERRIDES,
    _LINKED_ARTICLE_DOMAINS,
    POSTGRES_DSN,
    _linked_article_url,
    fetch_linked_article_body,
)

USERNAME = "intradaydotmy"
DELAY_SECONDS = 0.5  # polite pause between page fetches


def main() -> None:
    domain = _LINKED_ARTICLE_DOMAINS[USERNAME]
    display_name = _DISPLAY_NAME_OVERRIDES[USERNAME]
    conn = psycopg2.connect(POSTGRES_DSN)
    cur = conn.cursor()

    cur.execute(
        "UPDATE news_articles SET source_name = %s WHERE url LIKE %s AND source_name <> %s",
        (display_name, f"https://t.me/{USERNAME}/%", display_name),
    )
    renamed = cur.rowcount
    conn.commit()

    cur.execute(
        "SELECT id, full_body_text FROM news_articles WHERE url LIKE %s ORDER BY id",
        (f"https://t.me/{USERNAME}/%",),
    )
    rows = cur.fetchall()

    updated = no_link = failed = 0
    for row_id, body in rows:
        link = _linked_article_url(body or "", domain)
        if not link:
            no_link += 1
            continue
        article = fetch_linked_article_body(link)
        time.sleep(DELAY_SECONDS)
        if not article:
            failed += 1
            print(f"  fetch failed, kept teaser: id={row_id} {link}")
            continue
        cur.execute("UPDATE news_articles SET full_body_text = %s WHERE id = %s", (article, row_id))
        conn.commit()
        updated += 1
        if updated % 25 == 0:
            print(f"  ...{updated} expanded")

    cur.close()
    conn.close()
    print(
        f"Renamed {renamed} rows to {display_name!r}. Of {len(rows)} posts: "
        f"{updated} expanded with the article body, {no_link} had no {domain} link (unchanged), "
        f"{failed} failed (teaser kept)."
    )


if __name__ == "__main__":
    main()
