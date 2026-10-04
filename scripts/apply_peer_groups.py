"""Fill coins.peer_group (Postgres + Reflex SQLite mirror) from each coin's
business-model category via app/services/peer_groups.py. Idempotent; leaves
groups OpenRouter already chose (category_source = 'openrouter') alone.

    python scripts/apply_peer_groups.py
"""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.services.peer_groups import peer_group  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        db.execute(text("SET lock_timeout = '5s'"))
        rows = db.execute(
            text(
                "SELECT cmc_id, business_model_category FROM coins WHERE business_model_category IS NOT NULL "
                "AND (category_source IS NULL OR category_source <> 'openrouter' OR peer_group IS NULL)"
            )
        ).all()
        updates = [(peer_group(cat), cmc_id) for cmc_id, cat in rows]
        for group, cmc_id in updates:
            db.execute(text("UPDATE coins SET peer_group = :g WHERE cmc_id = :id"), {"g": group, "id": cmc_id})
        db.commit()
    finally:
        db.close()
    conn = sqlite3.connect(ROOT / "frontend" / "reflex.db", timeout=30)
    conn.executemany("UPDATE coin SET peer_group = ? WHERE cmc_id = ?", updates)
    conn.commit()
    conn.close()
    print(f"applied {len(updates)} peer groups ({sum(1 for g, _ in updates if g)} non-empty)")


if __name__ == "__main__":
    main()
