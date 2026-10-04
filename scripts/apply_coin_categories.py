"""Write the hand-labelled business-model categories (app/data/
coin_categories_claude.txt, `cmc_id|Category`, top 1,500 coins by market cap,
labelled by Claude Code on 2026-10-04) into Postgres and the Reflex SQLite
mirror. Idempotent. From then on app/services/coin_category_service.py
(OpenRouter) re-checks each coin weekly and labels new coins.

    python scripts/apply_coin_categories.py
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402

LABELS = ROOT / "app" / "data" / "coin_categories_claude.txt"
REFLEX_DB = ROOT / "frontend" / "reflex.db"


def main() -> None:
    labels: dict[int, str] = {}
    for line in LABELS.read_text().splitlines():
        if line.strip():
            cmc_id, category = line.split("|", 1)
            labels[int(cmc_id)] = category.strip()

    now = datetime.utcnow()
    db = SessionLocal()
    try:
        db.execute(text("SET lock_timeout = '5s'"))
        for cmc_id, category in labels.items():
            db.execute(
                text(
                    "UPDATE coins SET business_model_category = :c, category_source = 'claude-code', "
                    "category_checked_at = :t WHERE cmc_id = :id"
                ),
                {"c": category, "t": now, "id": cmc_id},
            )
        db.commit()
    finally:
        db.close()

    conn = sqlite3.connect(REFLEX_DB, timeout=30)
    conn.executemany(
        "UPDATE coin SET business_model_category = ? WHERE cmc_id = ?",
        [(c, i) for i, c in labels.items()],
    )
    conn.commit()
    conn.close()
    print(f"applied {len(labels)} categories")


if __name__ == "__main__":
    main()
