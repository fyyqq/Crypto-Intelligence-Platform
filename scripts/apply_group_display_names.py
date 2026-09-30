"""Applies telegram_pipeline._DISPLAY_NAME_OVERRIDES to Telegram posts that
were stored before an override existed (new posts get the short name at
ingestion). Idempotent; pure Postgres, no Telegram session, safe to run
alongside the listener.

Usage:
    source .venv/bin/activate
    python -m scripts.apply_group_display_names
"""

import psycopg2

from app.services.telegram_pipeline import _DISPLAY_NAME_OVERRIDES, POSTGRES_DSN


def main() -> None:
    conn = psycopg2.connect(POSTGRES_DSN)
    cur = conn.cursor()
    for username, name in _DISPLAY_NAME_OVERRIDES.items():
        cur.execute(
            "UPDATE news_articles SET source_name = %s WHERE url LIKE %s AND source_name <> %s",
            (name, f"https://t.me/{username}/%", name),
        )
        print(f"{username}: renamed {cur.rowcount} rows to {name!r}")
    conn.commit()
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
