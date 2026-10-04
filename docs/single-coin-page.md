# Single Coin Page

**Route:** `/coin/[symbol]` (ticker-based, e.g. `/coin/btc` — ties broken by market cap since tickers aren't unique on CMC) · **Status:** Live, actively evolving
**Source:** `frontend/frontend/components/coin_detail.py`, `state/coin_state.py`, `app/services/business_summary_service.py`, `description_ai_service.py`, `market_pairs_service.py`, `tradingview_symbol_service.py`

This page corresponds to the original "Feature 2: Knowledge Base & AI Business Model Agent" plan and the "Single Page Coin" idea sketched in this project's Notion workspace — but **the real implementation deviates from both in two structural ways**, by deliberate choice partway through building it:
- **No side-drawer/modal** — the AI content lives inline in the page itself, in the same layout position a "dummy sentiment" placeholder originally sketched for the right column.
- **No scheduled background worker** — every AI/data step below runs **on-demand**, triggered the first time a visitor opens that specific coin's page, not proactively for the whole Top 500 on a schedule.

Both are open architecture decisions — see `CLAUDE.md`'s Next Steps for the pending choice between formally adopting this as the real design vs. building the originally-planned pieces.

---

## Features

<details>
<summary><strong>💲 Price header</strong></summary>

Big real-time price, 24h % change, coin icon/name/ticker/rank. Same zero-price fallback as the homepage table (falls back to the coin's own top-volume real market pair when CMC's own price is exactly $0). Decimal display never rounds a real nonzero price down to "$0.00" regardless of how small — see this project's Coin Price Display Rule in `CLAUDE.md`.
</details>

<details>
<summary><strong>📈 Live TradingView chart</strong></summary>

A real, symbol-resolved TradingView widget — not a static image or something this app polls/caches; it's the same live-streaming chart technology tradingview.com's own site uses.

Symbol resolution, in order:
1. This coin's own real CEX market pairs, ranked by 24h volume with a real USD/USDT/other-stablecoin pair always outranking a foreign-fiat one regardless of volume (a high-volume Korean-Won pair on Upbit was confirmed live to otherwise beat a real but lower-volume USDT pair, making the chart's price look wrong next to this page's own USD header even though the listing itself was real — not a wrong-coin bug, just the wrong currency), mapped to TradingView's own exchange prefix — never a bare unprefixed guess, which was confirmed live to sometimes resolve to a completely different, malformed symbol.
2. If no real CEX pair exists, falls back to TradingView's own symbol-search API for a DEX pool match, filtered to real spot results and preferring one whose description actually names this coin, whose exchange label confirms the same on-chain platform when that's known, and whose own currency is USD when a choice exists — this closes a real bug where several tickers/names are reused by multiple unrelated real coins on different chains.
3. If neither resolves to a real listing, shows an honest "No live chart available for this coin" placeholder rather than TradingView's own broken-looking error card or a guess.

Default interval is 1 hour, clock shown in Kuala Lumpur time. Built as a real, stable React prop rather than a raw HTML string, so background data syncs elsewhere on the page don't tear down and rebuild the chart — that was previously resetting the viewer's manually-chosen interval roughly every 60 seconds.

The chart prefers whichever of MEXC, KuCoin, HTX, or Bybit (in that order) a coin actually has a real pair on, overriding the usual USD-equivalent-quote/volume ranking — a coin with just one of these four (e.g. only Bybit) still prefers it over a higher-volume Binance pair. Binance, Coinbase, or any other real exchange only get used via the normal ranking, and only when a coin has none of those four at all. An earlier version of this rule only kicked in when a coin had all three of MEXC, KuCoin, *and* Binance together — that left most real coins (which don't have all three) still defaulting to Binance, which is what this version fixes.
</details>

<details>
<summary><strong>🔒 Locked Supply section</strong></summary>

No free vesting/unlock-schedule API exists at any tier (CoinMarketCap has none; CryptoRank Pro is $4,750/yr; DeFiLlama's real emissions endpoint is Pro-only at $300/mo; CoinGecko's closest endpoint is also paid) — checked and confirmed paywalled before building anything. Shows `max_supply - circulating_supply` instead, as an honest supply-math-based fallback: locked amount, locked USD value at the current price, % of max supply, and a supply-range meter (green fill for the circulating portion). Rendered right after the Tags section, only when a coin actually has a max supply greater than its circulating supply — entirely absent otherwise (e.g. ETH, which has no max supply at all). Broadly applicable, not a rare edge case: roughly 1,700 of the top 2,000 ranked coins have a real supply gap.

Below the meter, a "View live unlock data" link — this app can't pull real unlock dates/schedules for free (same paywall as above), so this only ever links out to a real public, no-auth website for a human to read, never fabricated data. Resolving *which* page to link to for a given coin is itself real work, tried in three tiers:
1. **Real per-project DeFiLlama match** — DeFiLlama's own `/protocol/unlocks/<slug>` page for a project with a real, tracked vesting schedule. The `<slug>` comes from matching this coin's own on-chain contract address, then its CoinGecko id, then (last resort) its CMC id against DeFiLlama's public data — never a guessed slug from the coin's name (confirmed live that a naive guess breaks even for unambiguous names, e.g. "Arbitrum" → "arbitrum" 404s; the real page is "arbitrum-foundation").
2. **No DeFiLlama project match** (most coins — its Unlocks feature only tracks projects with a real vesting schedule to show) — links to **tokenomist.ai**'s own per-coin page (`tokenomist.ai/<gecko_id>/unlock-events`), a separate dedicated unlock-tracking site that may cover a project DeFiLlama's own Unlocks feature doesn't. Keyed by this coin's CoinGecko id, confirmed live that's tokenomist's real slug convention too (its ticker-based URL 404s: `/fet/unlock-events` fails, `/fetch-ai/unlock-events` is real) — reuses the exact same CoinGecko-id lookup tier 1 already depends on, no new external data source.
3. **No CoinGecko id known either** (coin outside that lookup's top-500 coverage) — falls back to DeFiLlama's own per-ticker **Token** page (`defillama.com/token/<TICKER>`) as the final safety net. Confirmed live this per-ticker page is real for any listed coin even with no unlock schedule at all — e.g. FET/Artificial Superintelligence Alliance has no Unlocks page under any slug, but `defillama.com/token/FET` is real.

Neither defillama.com nor tokenomist.ai's page-existence can be live-checked from this app's backend — both sit behind Cloudflare bot-protection that returns 403 to *any* plain scripted request, valid URL or not (confirmed via `curl` for both sites) — so each tier above is resolved from known-real data (contract/gecko-id/cmc-id matches, or a confirmed-real page pattern), never a live 404 probe.
</details>

<details>
<summary><strong>🤖 AI business summary</strong></summary>

On first visit, an on-demand call to OpenRouter (a free nemotron model — not Claude 3.5 Sonnet as originally planned, since that model is retired from OpenRouter and this project's OpenRouter account is free-tier) generates 3–4 titled paragraphs (the first is "Problem It Solves"). Re-generated periodically (60-day cache), not one-time, since a project's real business model can drift. Its CATEGORY: line only fills the badge for coins with no curated category (see below).
</details>

<details>
<summary><strong>🏷️ Business-model category badge</strong></summary>

The blue badge next to "&lt;Coin&gt; Live Chart" says what the project actually does (e.g. TAO "Decentralized Machine Learning", FET "Autonomous AI Agents", RENDER "Decentralized GPU Rendering", WILD "Open-World Metaverse Game").

- **Initial labels (Claude Code, 2026-10-04)**: the top 1,500 coins by market cap were labelled by hand from their name, CMC tags and description, stored in `app/data/coin_categories_claude.txt` (`cmc_id|Category`) and written by `scripts/apply_coin_categories.py` into `coins.business_model_category` (Postgres, `category_source = 'claude-code'`) and the Reflex SQLite mirror.
- **Weekly re-check (OpenRouter)**: `app/services/coin_category_service.py` runs on its own thread from `frontend/news_catchup.py`, one batch of 8 coins per `settings.coin_category_interval_minutes` (default 120). It picks coins whose `category_checked_at` is missing or older than 7 days (largest market cap first), sends each coin's name, ticker, tags, current category, CMC description and its own website text, and stores a 2–6 word answer (`category_source = 'openrouter'`). Answers naming listings/investors/ecosystems ("Binance Alpha", "… Portfolio", "… Ecosystem") or with the wrong length are rejected and that coin keeps its category. It counts against `ai_budget`'s hourly cap and backs off on failure. On the free tier (~50 requests/day) a full weekly pass over 1,500 coins needs ~27 calls/day, so it lags until the model is paid.
- **Fallback**: a coin with no category shows its first CMC tag that describes the project (e.g. "DeFi"); listing/investor/ecosystem tags (`_BADGE_NOISE_RE` in `coin_state.py`) are never shown, so with nothing suitable the badge is hidden.
- The business summary's CATEGORY: line never overwrites a curated category.
</details>

<details>
<summary><strong>📝 About section — real description upgrade</strong></summary>

Two independent, one-time upgrade steps replacing CMC's generic auto-generated boilerplate description: first, CoinGecko's own curated contract-address lookup if one exists for this coin; if still boilerplate after that (common for memecoins/new listings with no real whitepaper anywhere), a grounded AI paragraph generated from the coin's own website text and/or cached social posts, explicitly forbidden from inventing business-model/tokenomics/team details not present in the source text. Left untouched rather than fabricated when there's genuinely nothing to ground it in.
</details>

<details>
<summary><strong>💱 Real market pairs — Markets tab</strong></summary>

Real CEX and DEX trading pairs sourced from CoinGecko (CMC's own market-pairs endpoint 403s on this project's free API tier), filtered to each venue's real top-15 ranking and never padded if fewer real listings exist. USDC-quoted pairs are dropped in favor of the same exchange's non-USDC pair where one exists. Paginated 10 rows per page per tab, independently for CEX vs. DEX. The tab auto-switches to whichever side actually has real listings when the other is empty. Refreshed hourly, since exchange volume goes stale much faster than the AI summary or description above.
</details>

<details>
<summary><strong>🐦 X / social posts section</strong></summary>

UI-only right now — a horizontal slider of "View on X" cards linking to the coin's real X profile. Real post scraping was tried via two different third-party actors and later removed entirely per explicit request over cost and reliability concerns; the fallback-link UI that already existed for the "not scraped yet" case is now the permanent, only state.
</details>

<details>
<summary><strong>⭐ Watchlist star</strong></summary>

Next to the coin's name — gray outline when this coin isn't watched, filled amber when it is, toggled by `CoinState.toggle_watchlist`. Adding/removing here is what populates or empties the `/watchlist` page's own table. See [Watchlist](./watchlist.md) for the full feature.
</details>

---

## Known, accepted gaps

- No scheduled batch worker for the Top 500 and no side-drawer modal — both deliberate deviations from the original plan, not yet formally re-approved in the spec.
- A few real coins' TradingView charts correctly show "No live chart available" rather than a wrong chart, even though a real chart theoretically exists somewhere with a ticker/chain mismatch this app's matching logic can't safely resolve — treated as an acceptable trade-off, not a bug to chase further right now.
- **A real, not-yet-fixed bug**: NEAR Protocol's chart shows "No live chart available" even though NEAR trades on every major exchange — its own primary on-chain contract in this app's DB is mis-flagged to a bridged Ethereum representation instead of its native chain, so the Markets/chart data pipeline resolves off the wrong (DEX-only) token entirely. Lives in a different subsystem (`MarketDataService._upsert_contracts`'s primary-contract selection) from the TradingView-symbol logic elsewhere on this page.


### TradingView base/price guard (2026-10-01)
Chart symbols use the exchange pair's own base ticker when it is a plain ticker (e.g. Beam is `BEAMX` on MEXC/Binance), and pairs whose USD price is outside 0.5x-2x of the coin's price are ignored, so a same-ticker different coin can no longer be charted. Exchange priority (MEXC > KuCoin > HTX > Bybit) and USD-quote preference are unchanged.


<details><summary>Price Alerts section; fixed-size header icons</summary>

### 🔧 Follow-up: coin-page header icons fixed-size; Profile Score replaced by a price Alerts section (2026-10-04 session)
Per explicit request (`el-04..07`), **Feature 2 (coin page)**. **Icons**: the star and share icons next to the coin name shrank on long names (e.g. Artificial Superintelligence Alliance); they, and the coin image, now have `flex_shrink=0` and the name block `min_width=0`, so the name wraps instead (icons measured 18x18 on `/coin/fet`). **Alerts**: the dummy "Profile Score 57%" bar in `coin_detail.py::_info_column` is replaced by `_alerts_section` (bell + "Alerts", the list of this coin's price alerts, each "Price above/below $X" with an x to delete, and an "Add New Alert" button below). The button opens a centred dialog (`_alert_dialog`) with a USD price field; `CoinState.create_alert` validates server-side (number, > 0, < 1e12, max 10 per coin, no duplicate price), derives above/below from the coin's current price, and formats through `_fmt_usd`. Applies to every `/coin/[symbol]` page. **Limits**: alerts live in the browser session only (`CoinState.price_alerts`, lost on server restart, not saved per account) and are **not yet evaluated against live prices**, so nothing fires yet. **Verified live** on `/coin/fet`: dialog centred, invalid input shows the error, a valid price adds "Price above $0.3", Profile Score gone. Docs: `docs/single-coin-page.md`; Notion pending.

</details>


<details><summary>Triggered price alerts: popups, saved alerts, /alerts page</summary>

### 🔧 Feature: triggered price alerts — sliding popups, saved alerts, /alerts history page (2026-10-04 session)
Per explicit request. **Triggering**: `CoinState.start_alert_watch` (a background event added to the `on_load` of every page that has the floating widgets, guarded to one loop per session) checks the session's active alerts every 4s against live exchange prices (`frontend/live_prices.py`, same source as the watchlist popup; falls back to the synced price). A hit (price >= target for "above", <= for "below") removes the alert, adds it to the history, and shows a popup. **Popup** (`frontend.py::_alert_popups`): fixed, horizontally centred, 104px from the top (just under the header, the red-box spot), width up to 380px; always rendered so it can slide: `top` goes from `-1000px` to `104px` with a 0.7s transition, stays about 60s (re-armed by each new trigger), then slides back to `-1000px` and clears. Several triggers stack vertically (up to 5); each card has its own x that dismisses just that one (the whole stack hides when the last is closed). **Persistence**: new `price_alerts` table (`app/models/price_alert.py`, migration `c5d1e3f4a7b8`, FK to `users` ON DELETE CASCADE; `triggered_at` NULL = active) and `app/services/alert_service.py`. Logged in: alerts are saved on create/delete, loaded at login and on session restore, and marked triggered with the price seen. Logged out: alerts and history stay in the browser session only (lost on server restart). **Profile dropdown**: an **Alerts** row (bell) appears after login and opens the new `/alerts` page (`components/alerts_page.py`, `CoinState.load_alert_history`): the history of triggered alerts (coin, "Rose above/Fell below $X", price at that moment, KL time), newest first, with a "log in to keep your alerts" note for guests. **Floating star button** (`el-08`): back to the plain amber star icon (the three-stars SVG is deleted); the circle still turns white while the popup is open. **Verified live**: a guest ETH alert 0.03% above price triggered within a minute, the popup sat at 104px centred (x=735 of 1470) and slid out ~60s later; a logged-in test account's alert was saved in Postgres, triggered, dismissed with the x, and listed on `/alerts` from the database; the Alerts item appears in the dropdown only when logged in; zero console errors after fixing a hydration warning (a div nested in the callout's `<p>`). Test user deleted (`users`, `price_alerts` empty). **Limits**: alerts only fire while a browser tab is open (no background/email/push delivery); the live check reads public exchange tickers, which were partly blocked from this machine (HTX answered). Docs: `docs/global-components.md`, `docs/single-coin-page.md`; Notion pending.

</details>


<details><summary>Alerts: login-only, autofill, edit</summary>

### 🔧 Follow-up: price alerts are login-only (server-side guard), autofilled price, edit button (2026-10-04 session)
Per explicit request. **Login-only**: `coin_state._login_required` wraps every alert event (`open_alert_dialog`, `open_edit_alert`, `create_alert`, `delete_alert`, `load_alert_history`): a logged-out caller is redirected to `/login` and the handler never runs (checked on the server for every event). `CoinState.require_login` guards `/alerts` (on_load right after `restore_session`), `start_alert_watch` only runs for a logged-in account, guest in-memory alerts are gone, the coin page shows "Log in to add alerts" to guests, and the guest callout on `/alerts` was removed. **Autofill**: the add-alert dialog opens with the coin's current price (`_plain_price` = `_fmt_usd` precision without $ and commas). **Edit**: a pencil icon left of each alert's x opens the same dialog prefilled with that alert's price ("Edit price alert" / "Save alert"); saving recomputes above/below and updates the row (`alert_service.update_alert`). Verified live: guest `/alerts` -> `/login`; guest coin page shows the login button; logged in, the dialog prefilled 2684.19 (header $2,684.19), created an alert, edited it to 2500 -> "Price below $2,500.00", DB row updated. Test user deleted.

</details>


<details><summary>Badge row reversed, chain dropdown click fix, Problem It Solves</summary>

### 🔧 Follow-up: Narrative Radar badge row reversed; chain dropdown no longer opens the coin page; "Problem It Solves" in AI summaries (2026-10-04 session)
Per explicit request (`el-29..31`). **Narrative Radar cards** (homepage + `/narrative`): the badge row is `row-reverse` — time on the left, narrative + ticker badges on the right. **Coin table chain dropdown** (`coin_table._chain_badge`, also used by the `/watchlist` table): the popover is wrapped in a box with `on_click=rx.stop_propagation`, so opening the "Also deployed on" dropdown or clicking inside it no longer triggers the row's navigate-to-coin click (Radix portals the content, but React events still bubble through the component tree). The narrative badge has no dropdown, so this was the only one. **AI Summarizations** (`business_summary_service._SYSTEM_PROMPT`): now 3-4 paragraphs, the first always titled "Problem It Solves" (what problem/gap existed and why the project was created; meme coins say plainly they were made for fun/community). Existing summaries without that section and written before the change (`_PROBLEM_SECTION_SINCE`, 2026-10-03 18:30 UTC) are regenerated once on the next visit to the coin's page; newer ones are never force-refreshed, so a model that skips the section can't cause a regeneration loop. **Not yet visible**: OpenRouter's free daily quota (50 requests) is still exhausted until 08:00 KL; until then the old summary keeps showing (generation failures fall back to the cached text). Verified live: badge row computed `row-reverse` with time leftmost; clicking the chain dropdown and inside it stayed on `/`; service imports and app compiles.

</details>


<details><summary>X search link on Social Insights; Standard badge removed</summary>

### 🔧 Follow-up: "Standard" badge removed; Social Insights "See More" opens an X search for the coin (2026-10-04 session)
Per explicit request (`el-03/05`). **Header**: the grey "Standard" plan badge under the user's name in the logged-in profile pill is removed (`frontend.py::_profile_pill`; now just the name). **Coin page** (`coin_detail.py::_sentiment_column`): Social Insights' "See More" (was an inert `#`) now opens, in a new tab, an X search built per coin by `coin_state._x_search_url` (row field `x_search_url`): `$TICKER OR <chain>:<contract>` for a token, `$TICKER OR <chain>:native` for a coin with no contract — the same query X builds when you pick the coin from its search dropdown. Verified live: `/coin/btc` -> `https://x.com/search?q=$BTC OR bitcoin:native&src=typed_query`; `/coin/pons` -> `$PONS OR robinhood:0x39dbed3a2bd333467115de45665cc57f813c4571`; unit-checked FET -> `$FET OR ethereum:0xaea4…ad85` and SOL -> `$SOL OR solana:native`. **Limits**: X's chain slugs could not be verified live (X redirects logged-out visitors to its login page), so only slugs matching the user's examples / X's own dropdown are mapped (`_X_CHAIN_SLUGS`: ethereum, solana, base, arbitrum, polygon, optimism, robinhood, avalanche); a token on any other chain (e.g. BNB Smart Chain) falls back to a plain `$TICKER` search, and a native coin uses its main-chain name as the slug (`<name>:native`). Add a slug to `_X_CHAIN_SLUGS` once confirmed in X's dropdown. Only the Social Insights link was changed; the separate "View More" link above the X posts section still goes to the coin's own X profile.

</details>

<details>
<summary><strong>🧭 Similar Coins slider</strong></summary>

Above the Markets section, a slider of up to 10 coins with the same use case as the open coin, largest market cap first (e.g. SAND -> MANA, VR, TLM, WILD, ATLAS; FET -> VIRTUAL, PIEVERSE, KITE). Cards show icon, name, ticker, category badge, price, 24h change and market cap, link to the coin's page, and use the homepage news slider mechanics (arrows, drag, autoplay).

- **Peer groups** (`app/services/peer_groups.py`): 51 use-case groups. Each coin's business-model category maps to one group through ordered rules plus a small override list, written by Claude Code after reviewing all 1,121 category labels of the top 1,500 coins. Stored in `coins.peer_group` (Postgres + Reflex mirror) by `scripts/apply_peer_groups.py`.
- **Kept current by OpenRouter**: the weekly category check (`coin_category_service`) also returns a peer group chosen from the fixed `PEER_GROUPS` list (rules used if it names an unknown group); new coins get one when first categorised.
- **Fallback**: a coin without a group shows coins sharing its CMC narrative tag; with none, the section is hidden.
</details>

<details>
<summary><strong>📰 "&lt;Coin&gt; News" (real, targeted)</strong></summary>

Real articles from `news_articles` using the AI/rule coin targeting also behind the Narrative Radar: articles tied to this exact coin first (`target_cmc_id`), then articles whose narrative is one of the coin's own categories, newest first, up to 10. Cards show the ticker and narrative badges, time, title and excerpt and open the in-app reader; "More News" opens /narrative. With no match the section says no recent news mentions the coin or its narrative. The page's `on_load` runs `NewsState.load_news`, `track_coin_news` and `watch_new_articles`.
</details>

<details>
<summary><strong>🧭 Similar Coins: View More page</strong></summary>

The Similar Coins heading row is full width with a **View More →** link (indigo, same style as "More News") that opens `/coin/[symbol]/similar`: a back link to the coin, the group name, a "N coins" badge and a 5/3/2-column grid of every coin in the same peer group, largest market cap first, using the same cards as the slider. The chart column's sections are spaced 25px apart. (The 1m–1M timeframe button bar that was briefly added above the chart was removed again; favourite drawing tools and intervals cannot be preset in the free TradingView widget.)
</details>

<details>
<summary><strong>🕐 UTC clock</strong></summary>

A clock icon, "UTC" and a ticking HH:MM:SS sit right-aligned between the TradingView chart and the "&lt;Coin&gt; on X" section. `assets/chain_pills.js` updates `#utc-clock` every second from the viewer's device clock in UTC (no server call).
</details>

<details>
<summary><strong>🏷️ Accurate news categories and shared use-case news</strong></summary>

Every AI-targeted article gets an accurate label and, when the story is about a whole use case rather than one coin, a shared peer group (`app/services/news_category.py`; columns `target_narrative`, `target_group`). Examples: generic AI-agent stories -> "AI Agents" (shared), stablecoin industry news -> "Fiat-Backed Stablecoins" (shared), one exchange's hack -> "Security & Hacks" (not shared), SEC/Congress -> "Regulation & Policy" (not shared), Fed/market moves -> "Macro & Markets" (not shared), a story naming its coin -> that coin's peer group (not shared). The rules were written by Claude Code after reviewing the existing articles (with ~35 hand corrections); new articles are categorised by the same rules right after OpenRouter targets them. On a coin page, "&lt;Coin&gt; News" shows the coin's own stories first, then the shared stories of its peer group with the ticker badge switched to that coin (e.g. FET's AI-agent stories also appear on VIRTUAL as VIRTUAL). The Narrative Radar and /narrative keep each story's original top coin.
</details>

<details>
<summary><strong>🔗 Related News link and category/coin sliders (2026-10-05)</strong></summary>

The coin news section's "More News" link is now **"Related News"** and opens the coin's own category page `/narrative/<category>` (its peer group, e.g. `/narrative/ai-agents` for FET; a coin with no peer group uses its main narrative). Two pill sliders (same arrows/drag as the /news source filter) sit above the news section: **News categories** (orange pills, the categories this coin's stories fall under, its own category first, each linking to `/narrative/<slug>`) and **Coins in these stories** (indigo pills, the coins the radar tagged on those stories, most mentioned first, linking to each coin page; the open coin is left out, so the slider is hidden when every story is about the coin itself, e.g. BTC). Pill colours match a news card's category and ticker badges (theme-aware `--orange-*`/`--indigo-*` in `styles.css`). Applies to every coin page. `NewsState.coin_news_category_url`, `coin_related_categories`, `coin_related_coins`.
</details>
