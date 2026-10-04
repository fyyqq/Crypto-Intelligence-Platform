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


### Update (2026-10-01)
Homepage news strip cards show the title and time on one row (time at right). The coin table clips and scrolls horizontally at every width when its content is wider than its container (previously only <=1440px).


### Table overlay removed (2026-10-01)
The coin table root is flat/transparent at every width, so scrolled-in columns no longer show a darker area and vertical line past the table edge. Row hover highlight is unchanged.


<details><summary>Targeted Narrative + Coin (AI-targeted real news)</summary>

### 🔧 Feature: AI-targeted "Targeted Narrative + Coin" slider with real crypto news (2026-10-04 session)
Per explicit request. The homepage section's 20 dummy cards are replaced by real Cryptocurrency-category news, each tied by AI to ONE coin and its narrative (`app/services/news_targeting_service.py`). **AI due diligence (OpenRouter free model, same helper/fallbacks as the news summary)**: a batched prompt (10 articles per call) with a curated list of 45 narratives and each one's top-10 coins by market cap (CMC tags minus noise like VC portfolios, listings, chain ecosystems; wrapped/staked/bridged/stablecoin/tokenized coins excluded outside their own category). Rules: a story about a specific coin -> that coin; an industry/macro story -> the most affected narrative and one coin from its top 10 (prompt examples: Apple Vision Pro -> RENDER, Gensler leaving -> XRP, Larry Fink on tokenization -> ONDO); broad market -> BTC; otherwise none. **Validation**: a pick is kept only if it's in that narrative's top-10 list, or if the coin exists and is really mentioned in the text; anything else (hallucinated tickers, wrong narrative) is stored as "no target". Results live on `news_articles` (`target_symbol`, `target_cmc_id`, `target_narrative`, `target_reason`, `target_model`, `targeted_at`); each article is analysed once. Runs from `frontend/news_catchup.py`'s loop (one batch per 5-minute pass, last 72h, newest first) under `ai_budget`'s cap and failure cooldown. **UI** (`components/narrative_alerts.py`): text-only cards (source, time, narrative + ticker badges, title, 3-line excerpt) linking to the reader, in the same slider as the news strip (`news-slider-*`: drag, arrows, autoplay); `NewsState.home_targeted_news`; `watch_new_articles` now also refreshes when the number of analysed articles grows. **Not yet verified with the real AI**: OpenRouter's free tier allows only **50 requests/day in total** and it was already used up (mostly by the Telegram classifier during the backfill; resets 08:00 KL). Verified instead: parsing/validation with crafted answers (RENDER/XRP/ONDO examples accepted, NONE and a fake ticker rejected), and the UI with three articles labelled by hand through the same validation (cards rendered, auto-refreshed in 46s, zero console errors), then cleared. **Also fixed, found while testing**: `/news` froze because `NewsDB` left its connection idle in a transaction for a whole pipeline run while the listener's startup `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (which takes an exclusive lock even when the column exists) queued behind it, blocking every read. The pipeline connection is now autocommit, and all `ADD COLUMN` sites (`news_pipeline`, `telegram_pipeline`, `news_summary_service`, the new service) check `information_schema` first and use a 3s lock timeout.

</details>


<details><summary>30-day backfill of coin targets by Claude Code</summary>

### 🔧 Follow-up: last 30 days of Cryptocurrency news targeted by Claude Code (2026-10-04 session)
Per explicit request: the slider was empty (OpenRouter's free daily quota was used up), so the existing 30 days of Cryptocurrency news (2,798 articles) were labelled by hand by Claude Code in this session (no OpenRouter calls), and OpenRouter only handles new articles from now on. Each label went through the same `_validate` as the AI path (a pick must be in the narrative's top-10 list, or the coin must really be named in the text), stored with `target_model = 'claude-code'`. Rules used: coin named in the story -> that coin; macro/market moves -> BTC; SEC/CLARITY/US crypto policy and Ripple-linked figures (Gensler, Clayton, Peirce) -> XRP (ISO 20022); tokenization/RWA -> ONDO (Avalanche/Stellar/Chainlink when named); AI models/policy -> TAO, GPUs/AI compute -> RENDER, AI agents/agent payments -> FET; exchange hacks -> the exchange's token (BGB for Bitget); stablecoins -> USDC/USDT; pure geopolitics, ads, trade signals, scams, admin chat -> no target. Result: 2,798 analysed, 2,254 with a coin (BTC 937, XRP 228, ETH 168, USDC 113, ONDO 93, HYPE 88, BGB 74, ZEC 64, TAO 60, ...), 544 no target (7 of them because validation rejected a pick, e.g. "Pumpfun" doesn't name PUMP). `_validate` now falls back to the coin's own CMC tags (minus noise) for the narrative badge when a directly-named coin isn't in the curated lists. The slider shows the newest 50 targeted articles (`_HOME_NEWS_LIMIT`). Verified live: 50 cards, no images, newest first (NEAR / BTC / BGB / NEAR / BTC / TAO), zero console errors. Labels are judgments, not facts; they can be cleared per row (`targeted_at = NULL`) to let the AI redo them.

</details>


<details><summary>Homepage sliders: text-only cards, right-to-left autoplay</summary>

### 🔧 Follow-up: homepage sliders — text-only cards, right-to-left autoplay with the newest card on the right (2026-10-04 session)
Per explicit request (`el-20/21`). **Cryptocurrency strip**: compact cards (`news_page._news_card(compact=True)`) no longer show an image; they show the source badge again (Telegram group / website name), then title + time and the excerpt (no category badge). **Targeted Narrative + Coin**: the source badge is removed from every card; the ticker + narrative badges now share the top row with the time. **Autoplay** (`assets/chain_pills.js`, new `news-slider-rtl` class on both sliders): cards render oldest -> newest (`NewsState.home_crypto_news_rtl` / `home_targeted_news_rtl`), the slider opens at the right end with the newest card visible and drifts toward older cards, looping back to the right end; it re-anchors to the right whenever the card count changes (data loaded or refreshed). Pause on hover/drag/hidden tab unchanged. Verified live: both sliders 50 cards, 0 images, rightmost card newest, scrollLeft 13881 -> 13745 in 3s (moving toward older cards), zero console errors.

</details>


<details><summary>Right-to-left autoplay only on the Cryptocurrency strip</summary>

### 🔧 Follow-up: right-to-left autoplay only on the Cryptocurrency strip (2026-10-04 session)
Per explicit request (`el-22/23`): the `news-slider-rtl` mode stays on the homepage Cryptocurrency news strip only; the Targeted Narrative + Coin slider is reverted to newest-first order with the original left-to-right drift (`NewsState.home_targeted_news`, plain `news-slider-wrap`; `home_targeted_news_rtl` removed). Its card changes (no source badge, ticker/narrative + time row) stay. Verified live: strip opens at the right end with the newest card (40m ago) and drifts left (14205 -> 14066); targeted slider starts at the left with the newest card (1h ago) and drifts right (9 -> 149); zero console errors. Note: one server start failed with the known transient `Prerender: Request failed for /: ... timeout` build error; a retry succeeded.

</details>


<details><summary>Narrative Radar section and strip direction revert</summary>

### 🔧 Feature: Narrative Radar — homepage section renamed, "More Narratives" link, real `/narrative` page; news strip back to left-to-right (2026-10-04 session)
Per explicit request (`el-24..28`). **News strip**: the right-to-left autoplay is fully reverted (newest card first, original left-to-right drift; `news-slider-rtl` JS branch and `home_crypto_news_rtl` removed) and its "More News" link now goes to `/news/cryptocurrency` (was `/news#cryptocurrency`). **Homepage section**: "Targeted Narrative + Coin" is now **"Narrative Radar"**, with a "More Narratives →" link at the right of the heading row (same style as "More News") to `/narrative`. **`/narrative` page** (the header's Narrative link; previously a blank placeholder): `narrative_alerts.narrative_page_content` lists every AI-targeted Cryptocurrency article (`NewsState.narrative_view`), newest first, 100 cards per page in the same 5/3/2-column grid and first/prev/next/last pagination as a `/news/<category>` page, with a centred "Narrative Radar" title, one-line description and article count; cards are the same text-only ticker + narrative cards as the homepage (full grid width). Title "Repace — Narrative Radar"; on_load loads the news and resets to page 1. Verified live: strip drifts left-to-right (232 -> 367), links correct, header Narrative link opens `/narrative` with 100 cards in 5 columns, "Showing 1–100 of 2254", next page -> 101–200 / Page 2 of 23, zero console errors.

</details>


<details><summary>Badge row reversed, chain dropdown click fix, Problem It Solves</summary>

### 🔧 Follow-up: Narrative Radar badge row reversed; chain dropdown no longer opens the coin page; "Problem It Solves" in AI summaries (2026-10-04 session)
Per explicit request (`el-29..31`). **Narrative Radar cards** (homepage + `/narrative`): the badge row is `row-reverse` — time on the left, narrative + ticker badges on the right. **Coin table chain dropdown** (`coin_table._chain_badge`, also used by the `/watchlist` table): the popover is wrapped in a box with `on_click=rx.stop_propagation`, so opening the "Also deployed on" dropdown or clicking inside it no longer triggers the row's navigate-to-coin click (Radix portals the content, but React events still bubble through the component tree). The narrative badge has no dropdown, so this was the only one. **AI Summarizations** (`business_summary_service._SYSTEM_PROMPT`): now 3-4 paragraphs, the first always titled "Problem It Solves" (what problem/gap existed and why the project was created; meme coins say plainly they were made for fun/community). Existing summaries without that section and written before the change (`_PROBLEM_SECTION_SINCE`, 2026-10-03 18:30 UTC) are regenerated once on the next visit to the coin's page; newer ones are never force-refreshed, so a model that skips the section can't cause a regeneration loop. **Not yet visible**: OpenRouter's free daily quota (50 requests) is still exhausted until 08:00 KL; until then the old summary keeps showing (generation failures fall back to the cached text). Verified live: badge row computed `row-reverse` with time leftmost; clicking the chain dropdown and inside it stayed on `/`; service imports and app compiles.

</details>


<details><summary>Narrative Radar targeting catch-up (offline / restart / refresh)</summary>

### 🔧 Follow-up: Narrative Radar targeting now catches up after offline / restart / refresh (2026-10-04 session)
Per explicit request (`el-01/02`): the Narrative Radar list lagged behind the news strip because new articles only got a coin when the AI targeting pass ran — which waited behind the slow RSS / Google News pull, handled 10 articles per 5-minute pass, ran nothing at start-up, and did nothing at all when OpenRouter was rate-limited. **Fix** (`frontend/news_catchup.py`, `app/services/news_targeting_service.py`): targeting now has its own worker thread (`_targeting_loop`) that runs at server start-up, every 2 minutes, and whenever a page load kicks it (`ensure_running()` is called on every `/news`/homepage `load_news`, debounced to once per 20s). Each run `drain()`s the whole untargeted backlog (last 72h, newest first): AI batches of 10 until none are left. **No-AI fallback**: if OpenRouter is unavailable (daily quota / outage; the shared `news-targeting` failure cooldown), `target_by_rules` instantly targets articles that explicitly name a coin — a `$CASHTAG` or the full coin name of the top ~400 by market cap (bare tickers like AI/ME/OP are deliberately not matched) — with `target_model = 'rule'`; articles without an explicit mention are left untouched so the AI picks them up when it is back. **Verified live**: OpenRouter's quota had reset; draining took the 72h backlog from 36 untargeted to 0 (AI picks e.g. BTC / ONDO / BNB); then, to simulate an offline gap, the 8 newest AI labels were cleared, the server was restarted and the homepage loaded — all 8 were re-targeted within about a minute and the slider rendered 50 cards in 7s; rule matching unit-tested ("Solana ETF" -> SOL, "$XRP" -> XRP, "Chainlink" -> LINK; "AI model", "ME page" -> none). The Telegram listener was also started by the same catch-up (one process). **Limits**: rule matches are explicit mentions only, so some articles stay untargeted until the AI is available; the AI free tier still allows only ~50 requests/day shared with the Telegram classifier.

</details>


<details><summary>Coin rows and results are real links</summary>

### 🔧 Follow-up: coin rows and results are real `<a href>` links, not click handlers (2026-10-04 session)
Per explicit request (`el-06/07`): anything that moves to another page is now a plain anchor tag, so middle-click, Ctrl/Cmd-click and "open in new tab" work, instead of a Reflex `on_click` (`go_to_coin` / `go_to_coin_from_search`) that ran `window.location.assign`. **Coin table + `/watchlist` table** (`coin_table.py::_name_link`, `coin_href`; `watchlist_table.py`): the icon + name + ticker is an `rx.link(href="/coin/<symbol>")`; a CSS stretched link (`assets/styles.css`: `.coin-row-linked` is `position: relative`, `.row-link::after` covers the whole row) makes the entire row the link; the row's `on_click` is gone. The star cell and the "Also deployed on" chain dropdown carry `.row-interactive` (`z-index: 1`) so they stay separate controls and don't navigate. **Floating watchlist popup rows** (`frontend.py::_watchlist_popup_row`) and **header search results** (`global_search.py::_global_search_result_row`) are now `rx.link` rows. Because a search-result link no longer clears the typed query via a handler, `CoinState.restore_session` (first `on_load` on every page) now clears `global_search_query` on the next page load. Cards that already were links (news cards, Narrative Radar cards, alert rows, "More …" links) are unchanged; remaining handler-based navigations are actions rather than links (post-login/logout redirect, the logged-out avatar's width-dependent redirect-or-dropdown). The existing document click listener (`chain_pills.js`) still turns plain same-origin anchor clicks into full page loads, so behaviour for a normal click is unchanged. **Verified live**: row link `<a href="/coin/btc">`; elementFromPoint on the rank and price cells hits the row link, on the star cell hits the star (not a link); the chain dropdown opens without leaving the page; search results are `<a href="/coin/btc">` etc.; the watchlist popup row is `<a href="/coin/btc">`; zero console errors. (`.to(str)` is needed before `.lower()` on an untyped dict value inside a foreach.)

</details>

<details>
<summary><strong>🧱 Overview cards row (placeholders)</strong></summary>

Four equal-height (260px) empty bordered cards in one row above the Cryptocurrency news strip (`components/market_overview.py`, 4 columns from lg width, 2 from sm, 1 on phones). They are layout placeholders for Market Status / Trending Coins / Derivatives / promo content and are intentionally empty for now.
</details>
