# Chains

**Route:** `/chains` · **Status:** Index of every chain (2026-10-15)
**Source:** `frontend/frontend/frontend.py::chains_page`, `components/index_pages.py`

Shows a "Chains" heading with a count and **every chain as a pill, all on one page (no pagination)** — the same list the homepage "More Chain" pages through (`CoinState.chain_names`). Clicking a pill selects that chain in the homepage filter and goes to `/` (`CoinState.open_chain`).

**24h ranking (2026-10-15):** pills are sorted by each chain's 24h score, shown at the right of its name (green up / red down): the plain average 24h change of its **top 20 coins by market cap** that have a 24h change (at least 3, otherwise no number and listed after the scored ones by size). Changes come from our own hourly `price_snapshot` rows (top 500 coins, under $50K volume left out; same data as Gainers & Losers), so it costs **no API call**; the result is cached for every session and recomputed at most **hourly** (the snapshots only change hourly; 10 min while the 24h window is still collecting). Code: `app/services/sector_performance_service.py` (tests `tests/test_sector_performance.py`), `coin_state.sector_boards` / `CoinState.load_sector_boards`, `components/index_pages.py`.

**Not to be confused with:** the [Home](./home.md) page's own chain pill filter — that's a Home feature. An early planning note in this project's Notion workspace called this idea the "Blockchain Page" — scope not yet decided.
