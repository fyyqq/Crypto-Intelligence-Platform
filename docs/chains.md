# Chains

**Route:** `/chains` · **Status:** Index of every chain (2026-10-15)
**Source:** `frontend/frontend/frontend.py::chains_page`, `components/index_pages.py`

Shows a "Chains" heading with a count and **every chain as a pill, all on one page (no pagination)** — the same list the homepage "More Chain" pages through (`CoinState.chain_names`). Clicking a pill selects that chain in the homepage filter and goes to `/` (`CoinState.open_chain`).

**Not to be confused with:** the [Home](./home.md) page's own chain pill filter — that's a Home feature. An early planning note in this project's Notion workspace called this idea the "Blockchain Page" — scope not yet decided.
