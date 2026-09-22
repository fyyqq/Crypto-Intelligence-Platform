"""Manual/backward-compat entrypoint for the Postgres -> Reflex SQLite port.

The 24h scheduler (app/scheduler/jobs.py) now calls
app.services.reflex_cache_service.sync_reflex_cache() automatically after
every successful CMC listings sync. Run this script directly only if you
need to force a re-sync outside that schedule (e.g. right after manually
running a sync).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.reflex_cache_service import sync_reflex_cache  # noqa: E402


def main() -> None:
    categories_count, coins_count = sync_reflex_cache()
    print(f"Ported {categories_count} categories and {coins_count} coins into frontend/reflex.db")


if __name__ == "__main__":
    main()
