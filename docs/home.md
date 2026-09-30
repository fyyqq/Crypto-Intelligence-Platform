# Home

**Route:** `/` · **Status:** Live, feature-complete
**Source:** `frontend/frontend/frontend.py::index`, `components/coin_table.py`, `components/filters.py`, `components/news_feed.py`, `components/narrative_alerts.py`

Reflects the actual shipped implementation as of 2026-09-27. The original plan lives in `CLAUDE.md`'s older `### Feature 1: Dynamic Market Data Sync & Dashboard` section for historical reference — this page tracks what's really built, and gets updated every time that changes (see this project's `CLAUDE.md` **Documentation Sync Rule**).

---

## Features

<details>
<summary><strong>📊 Coin listing table</strong></summary>

All ~8,193 CMC-tracked coins, 11 columns always visible (never hidden by screen size): a leading Watchlist star, Rank, Name (icon + name + ticker + narrative/chain badges), Price, Market Cap, 24H Volume, 1H/24H/7D % change, 24H/7D trend sparklines. Market-cap-ranked by default, every column sortable by clicking its header (3-state cycle: desc → asc → back to default order). Horizontal scroll is the fallback when the table is wider than its column — the table itself never hides a column regardless of screen width.
</details>

<details>
<summary><strong>⭐ Watchlist star column</strong></summary>

New leftmost column, before Rank — same toggle design as the coin-detail page's own star and the `/watchlist` page's own remove star: gray outline when a coin isn't watchlisted, filled amber when it is, reading/writing the same `CoinState.watchlist_ids`/`toggle_watchlist(cmc_id)` every other watchlist entry point uses. Clicking it toggles that one coin's membership without navigating to its detail page (`rx.stop_propagation` on the click). Lets a coin be starred straight from the browsing table, not just from its own detail page.
</details>

<details>
<summary><strong>🔢 Pagination</strong></summary>

50 / 100 / 200 / 500 rows per page, previous/next arrows plus a numbered page-window control.
</details>

<details>
<summary><strong>🏷️ Narrative & chain filters</strong></summary>

Two pill rows in the left sidebar — top 20 narratives and top 20 chains, each ranked by how many coins on the platform carry that tag (recomputed on every full sync, not a fixed list). AND-combined (e.g. "Memes" + "BNB Smart Chain" narrows to memecoins on BNB specifically). "More Narrative"/"More Chain" expands to *every* narrative/chain that exists (574 / 819 respectively as of this writing) with no second query — both the top-20 and full lists are computed once, up front — and the same pill becomes "Show less" to collapse back to the default view.
</details>

<details>
<summary><strong>🔍 Table search</strong></summary>

Name/ticker search across the entire coin universe, not just the current page. Desktop: icon-triggered popover next to the table heading. Mobile (below 768px): always-visible full-width field in its own row. Debounced 300ms. Distinct from the header's own global search (see [Global Components](./global-components.md)) — this one only re-filters this table in place.
</details>

<details>
<summary><strong>💀 Skeleton loading</strong></summary>

A deliberately-visible (roughly 150–250ms) loading skeleton on every filter/search/pagination change, even though the underlying re-filter of an in-memory list is itself instant — without the artificial delay it would flash for under a millisecond and never actually register as loading feedback.
</details>

<details>
<summary><strong>📰 News feed & targeted narrative alerts</strong></summary>

Two horizontal drag-scroll sliders above the table: "All News" (static placeholder headlines — no real news backend exists yet) and "Targeted Narrative + Coin" alerts (narrative-tagged, linking a headline to the specific coin it's about). Both scroll at every viewport width via drag or the always-visible arrow buttons.
</details>

<details>
<summary><strong>⚡ Live data sync</strong></summary>

Three-tier backend sync: a 24h full-universe sync (catches new listings), a 1h "hot" sync for the top 500 coins' quotes, and a 60-second view-driven sync that only refreshes whichever roughly 100 coins are actually on-screen right now (also re-triggered immediately on any filter/search/pagination change, not just the timer). Prices and market caps update in place without a page reload.
</details>

<details>
<summary><strong>💲 $0.00 price fallback</strong></summary>

If a coin's canonical CMC price is exactly zero (a real, if uncommon, CMC data gap — confirmed by direct query, around 416 coins in this dev database), the table falls back to that coin's own already-fetched top-volume real market-pair price instead of showing a flat "$0.00" — the same fallback the coin's own detail page uses. Only applies once a coin has been visited at least once, so its market pairs are cached.
</details>

---

## How data flows onto this page

`CoinState.load_coins` fetches the full coin universe **once per browser session** — skipped on every subsequent navigation back to this page, confirmed live this was previously costing around 2 seconds of blocking server time per visit. Live updates from the sync tiers above land in a small per-coin override dict holding only the fields that actually changed, merged into the full row set at render time, rather than ever re-sending the entire roughly 32MB serialized coin list over the websocket again after the first load — confirmed live this was the dominant fix behind "every click on this page feels slow."

The header/navbar, footer, and the header's own global search also render on this page, but are documented in [Global Components](./global-components.md) since they're shared by every page in the app, not specific to Home.

<details><summary>Live news strips (replaces the dummy news feed)</summary>

The homepage shows two sliders, "Cryptocurrency" and "Markets & Finance", each with the 15 newest real `/news` cards for that category (same card component, same rows, same 60s live refresh via `NewsState`). "More News" links to the matching `/news` section. Skeleton cards show while the news list loads.

</details>

<details><summary>News strip cards, autoplay</summary>

The homepage news strips show 50 compact cards each (no image; the source-group and category badges hidden, only the Telegram badge, time, title and snippet). Both autoplay one card every 3.5s, looping at the end, and pause while hovered (cards or arrows), while dragging, or when the tab is hidden. The "More Impact" link on the Targeted Narrative section was removed.

</details>

<details><summary>News strip update: single strip, continuous autoplay</summary>

The homepage now has a single news strip (Cryptocurrency, 50 compact cards); the Markets & Finance strip was removed. Autoplay is a continuous drift (about 45px/s), not card-by-card, looping at the end, and pausing on hover, drag or a hidden tab.

</details>

<details><summary>News strip cards show images again</summary>

The homepage news cards show the post's own image (else the group's profile picture, else the category fallback) again; only the source-group and category badges stay hidden.

</details>
