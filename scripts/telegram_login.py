"""
One-time interactive Telegram login for app/services/telegram_pipeline.py.

Run this yourself, directly in your own terminal — it will ask for your
phone number, then the login code Telegram sends you (and your 2FA
password too, if you have one enabled). None of that goes through Claude;
this script only talks to Telegram directly.

Usage:
    source .venv/bin/activate
    python scripts/telegram_login.py

On success it saves a local session file (telegram_session.session, at
the repo root — already gitignored, never commit it) that
telegram_pipeline.py reuses afterward with no further login needed.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from telethon.sync import TelegramClient

load_dotenv()

API_ID = int(os.environ["API_ID_TELEGRAM"])
API_HASH = os.environ["API_HASH_TELEGRAM"]
# Anchored to the repo root regardless of the current working directory —
# must match app/services/telegram_pipeline.py's own SESSION_PATH exactly,
# or the pipeline won't find the session this script creates.
SESSION_PATH = str(Path(__file__).resolve().parents[1] / "telegram_session")

if __name__ == "__main__":
    with TelegramClient(SESSION_PATH, API_ID, API_HASH) as client:
        me = client.get_me()
        print(f"Logged in as: {me.first_name} (@{me.username or me.id})")
        print(f"Session saved to {SESSION_PATH}.session — you're done, no need to run this again.")
