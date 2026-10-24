# Single Coin Page

**Route:** `/coin/[symbol]` (ticker-based, e.g. `/coin/btc` — ties broken by market cap since tickers aren't unique on CMC) · **Status:** Live, actively evolving
**Source:** `frontend/frontend/components/coin_detail.py`, `state/coin_state.py`, `app/services/business_summary_service.py`, `description_ai_service.py`, `market_pairs_service.py`, `tradingview_symbol_service.py`

**Coin URLs (2026-10-15):** a coin's page is `/coins/<name>` (`/coins/ethereum`, `/coins/a-meme-coin`; the slug is the coin's name lower-cased with non-alphanumerics as `-`). Names are not unique either, so the biggest coin (market cap, then lowest CMC id) keeps the plain name and the others get `-2`, `-3`… (172 of ~8,300 coins today); a name with no Latin letters/digits falls back to the ticker. `coin_state.assign_slugs` sets `row["slug"]` when the coin list is built, `pick_coin` resolves the route, and every link (table rows, header search incl. the instant results from `/api/coin-index`, watchlist, similar coins `/coins/<name>/similar`, Gainers & Losers, home movers, alerts) uses it. The numbering can change if a duplicate-name coin overtakes another in market cap. **Old links** (`/coin/eth`, `/coin/meme-42007`, saved notifications) still work: `/coin/[symbol]` is a small page that redirects to the new path (`CoinState.redirect_legacy_coin`). Tests: `tests/test_coin_slugs.py`.

**Your MEXC box (2026-10-16, local only):** above Alerts in the left column, for `MEXC_VIEWER_EMAILS` accounts only: your MEXC holding of the coin (amount, value, average buy, P/L) and its open limit/stop orders, every 15 s. On such a coin the main chart area opens on "My lines" (Lightweight Charts of the MEXC pair: avg buy blue, limit green, stop-loss red dashed) with a My lines / TradingView switch (`PortfolioState.coin_mexc_loop`, `portfolio_page.py::coin_mexc_section`). Hidden for everyone else. Details: [Portfolio](./portfolio.md).

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

Default interval is 1 hour, clock shown in Kuala Lumpur time. The preset strip above the chart (1m, 5m, 15m, 1h, 4h, D, W) is **hidden on the coin page since 2026-10-15** (`timeframe_controls(..., hidden=True)`: opacity 0, width 0, height 0, overflow hidden; the buttons stay in the DOM so `tradingview_timeframes.js` is unaffected, and `/tools/market-charts` still shows them); TradingView's own interval bar inside the chart is what switches intervals. The iframe is built as a real, stable React prop rather than a raw HTML string, so background data syncs elsewhere on the page don't tear down and rebuild the chart or reset the selected interval.

The chart prefers whichever of MEXC, KuCoin, HTX, or Bybit (in that order) a coin actually has a real pair on, overriding the usual USD-equivalent-quote/volume ranking — a coin with just one of these four (e.g. only Bybit) still prefers it over a higher-volume Binance pair. Binance, Coinbase, or any other real exchange only get used via the normal ranking, and only when a coin has none of those four at all. An earlier version of this rule only kicked in when a coin had all three of MEXC, KuCoin, *and* Binance together — that left most real coins (which don't have all three) still defaulting to Binance, which is what this version fixes.

The chart fills the full width of its available column: the three-column desktop layout uses the entire flexible center column, and below the large-screen breakpoint the stacked chart uses the full padded page width. Its height remains responsive by breakpoint, and the iframe scales to the wrapper without forcing horizontal page overflow. This sizing is shared by every coin route.
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

**Free-tier daily limit (2026-10-15):** OpenRouter's free models allow 50 requests a day per account (reset 00:00 UTC), shared by live, local dev and the background jobs. When it is used up every summary (coin and news pages) silently shows nothing. `app/services/ai_budget.py` now keeps a daily counter on disk (`logs/ai_budget.json`, `OPENROUTER_DAILY_LIMIT` 50, 0 = unlimited): page-visit summaries own the last `OPENROUTER_VISIT_RESERVE` (30) calls of the day while background work (Telegram post classification, news targeting, the weekly category check) stops earlier; the first "free-models-per-day" 429 pauses all calls until OpenRouter's reset (no wasted retries/fallback calls, no 30-minute item cooldown). The dead `qwen/qwen3.8-27b:free` fallback (404) was replaced. Adding 10 OpenRouter credits lifts the account to 1000 free-model requests a day (then set `OPENROUTER_DAILY_LIMIT=0` or 1000).
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

Real articles from `news_articles` using the AI/rule coin targeting also behind the Narrative Radar: articles tied to this exact coin first (`target_cmc_id`), then articles whose narrative is one of the coin's own categories, newest first, up to 10. Cards show the ticker and narrative badges, time, title and excerpt and open the in-app reader; "Related News" opens the coin's category page (`/narrative/<category>`). With no match the section says no recent news mentions the coin or its narrative. The page's `on_load` runs `NewsState.load_news`, `track_coin_news` and `watch_new_articles`.
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
<summary><strong>🔗 Related News link (2026-10-05)</strong></summary>

The coin news section's link reads **"Related News"** and opens the coin's own category page `/narrative/<category>` (its peer group, e.g. `/narrative/ai-agents` for FET; a coin with no peer group uses its main narrative). Applies to every coin page (`NewsState.coin_news_category_url`). Two pill sliders (news categories, coins in the stories) were added above the news on the same day and removed again at the user's request.
</details>

<details>
<summary><strong>📊 24h change on Market cap and Volume (2026-10-05)</strong></summary>

In the stats box, Market cap and Volume (24h) show a small CMC-style change under the value (e.g. "▲ 15.09%" green, "▼ 3.20%" red), with a tooltip naming the old value and its time. It is the app's own number, not CMC's: the coin's current value (refreshed every 60s by `CoinState.detail_sync_loop`) against our own `price_snapshot` row from about 24h ago (`price_snapshot_service.get_reference_values`: the snapshot closest to now − 24h inside 20–28h, chosen separately for each field), using the same `pct_change` formula and 24h window config as the Gainers & Losers board. Computed on page load (`CoinState.refresh_change_24h`) and again on every 60s tick; shown only for the coin that is open (`change_24h_view`).

**Coverage:** snapshots now hold market cap too (`price_snapshot.market_cap`, migration `a9b5c7d8e2f4`). Every coin gets a daily snapshot from the full listings sync (`jobs.run_listings_sync`, all ~8,200 coins, ~41 CMC credits/day), and the top 500 also hourly, both run from the Reflex process (`news_catchup._hot_sync_loop`). Nothing is shown until a snapshot about 24h old exists: volume from about 20h after 2026-10-05 04:48 UTC (top 500), market cap from about 20h after the first sync with market cap, and for coins ranked below 500 about a day after the first daily full sync. No values are invented in the meantime.
</details>

<details><summary>Live header price, every second (2026-10-13)</summary>

`CoinState.coin_live_price_loop` reads the last traded price of the chart's own exchange pair every second (`frontend/live_prices.py`, one kept-alive HTTP client; falls back to OKX, Gate, MEXC, KuCoin, HTX, Bybit, Binance by ticker with the 0.5x-2x plausibility check; an unreachable exchange is skipped for 5 minutes). It is fetched on the server (Binance/Bybit are blocked from Malaysia, so a browser-side stream would fail for a Malaysian viewer) and pushed as one small string var (`live_price_display`), so a tick costs a few bytes and never recomputes the big coin vars. The price flashes green/red on each change (`.price-flash-up/-down`) and a pulsing dot marks it live; until the first tick the synced price shows. `detail_sync_loop` refreshes the rest of the coin (24h change, market cap) every 30s from the shared exchange price list, with CoinMarketCap only as the fallback. The coin page used to receive ~221 MB per 30s (the full coin list re-sent on each update); now ~2.3 MB.
</details>

<details><summary>Load time (2026-10-13)</summary>

A direct load of a coin page renders only after its on-load events finish (Reflex hydrates dynamic routes that way), so their cost is the page's load time. Measured on a fresh session: 13.5s before, ~1.2-3.3s after. What changed: (1) session state lives in memory, not a ~22 MB pickle rewritten to disk on every event (`rxconfig.py`); (2) the coin list is built once per server and shared (`coin_state.ensure_universe`, 10-min TTL, with an id index), and pre-built at server start (`frontend.py::_warm_caches` lifespan task, also warms the exchange price list), so the first visitor after a restart doesn't pay ~20s; (3) the background refreshers (description, AI summary, market pairs, chart symbol, unlocks) and `_apply_updates` only write `coin_overrides` when a value actually changed (`_set_override` / `_differs`), because every write made Reflex recompute and re-send ~240 KB of coin vars (~1s each).
</details>

<details><summary>Chart symbol: CEX first, DEX only on the coin's own chain (2026-10-13)</summary>

With no cached CEX pair, the chart symbol comes from TradingView's own search (`tradingview_symbol_service._pick_best_match`): first a centralized-exchange spot listing `{TICKER}{USDT|USDC|USD|FDUSD}` whose description names the coin (Binance, OKX, Bybit, Bitget, Gate, KuCoin, MEXC, HTX, Coinbase, Kraken first, then any other CEX such as KCEX), with no chain check; only then a DEX pool, and only one on the coin's own chain (its contract platforms, or its "X Ecosystem" category when no contract is stored). With no chain hint and pools on several chains, no chart rather than the wrong coin. Fixed: CyberLeek (Solana-only) had been charted from a Uniswap pool on Base, now `KCEX:CYBERLEEKUSDT`; CGPT from a Base pool, now `BINANCE:CGPTUSDT`.

The 1-second header price falls back, when no supported exchange lists the coin, to its own contract's deepest DEX pool on DexScreener (free, no key, cached 3s; `live_prices._dex_price`). CyberLeek: $0.0025 live, while the stored CMC price was stale. TradingView's `GATE`/`HUOBI` prefixes map to our `GATEIO`/`HTX`; the chart's own pair is accepted within 0.2x-5x of the stored price (a stale stored price no longer blocks a real move).

The coin page's X section (and links) needs the coin metadata from CMC's `/v2/info` (`sync_contracts`), which only the never-running FastAPI scheduler used to call, so the live server had no X links or contracts at all. It now runs weekly from the hot-sync loop (`jobs.run_metadata_sync`, behind the CMC credit guard).
</details>

<details><summary>Chart header gap, empty-news height and tablet width (2026-10-15)</summary>

- **Gap under the chart header.** The hidden timeframe strip (below) was a direct child of the chart column, which has a 25px row gap, so even at zero size it added a second 25px gap between "<Coin> Live Chart" and the chart. It now sits **inside the chart box** (`coin_detail.py::_chart_column`), `position: absolute`, 0x0, opacity 0, `pointer-events: none`; it is still inside the `[data-tv-chart]` column, so `tradingview_timeframes.js` still works (verified: clicking a hidden button changes the iframe interval). Measured: header-to-chart gap 25px at every width.
- **Empty news box.** "Targeted narrative news" is a fixed 585px box (it lines up with the sentiment column beside it on desktop). With no news it left a big blank area on tablet and mobile, so the box now gets the class `coin-news-empty` when `NewsState.has_coin_news` is false and `@media (max-width: 1279px)` sets `height: max-content` (`styles.css`): 47-67px instead of 585px below 1280px, still 585px on desktop and whenever there is news. Applies to every coin page (one component).
- **Sideways scroll on tablets in landscape.** The centre (chart) column wrapper was `width: auto` from `md` (1024px) although the three columns only sit side by side from `lg` (1280px), so between 1024 and 1279px the stacked column was as wide as its widest unbroken text (the About paragraph, 2540px) and the page scrolled sideways. It is now `width: 100%` until `lg` (`width=["100%","100%","100%","100%","auto"]`). Verified at 1440 / 1280 / 1180 / 1100 / 1024 / 834 / 375, light and dark, on a coin with and without news: no horizontal scroll.
</details>

<details><summary>Chart symbol: TradingView's Crypto tab, name first, no wait (2026-10-15)</summary>

Some coins (e.g. `/coin/si`, Super Inu) never showed a chart: the loading state stayed forever. Two causes, both fixed:
1. **Same-ticker coins.** `/coin/si` is Super Inu *and* Sealwifhat, both $0 market cap. The page shows one, but every per-coin background lookup (description, AI summary, market pairs, chart symbol, unlocks) picked "the biggest coin with this ticker" in Postgres, which was the other one, so the shown coin's "lookup finished" flags never turned on. All five (`_fetch_*` in `coin_state.py`) now take the cmc_id of the coin the page shows (`_page_coin`; ticker only as a fallback).
2. **Slow, noisy search.** The chart search used to wait for a CoinGecko market-pairs round trip and then searched TradingView with the bare ticker across every market ("SI" = silver futures and stocks, 6.5s, no crypto match). `tradingview_symbol_service` now searches **TradingView's Crypto tab** (`search_type=crypto`, ~0.3-0.8s), **the coin's name first** ("Super Inu"), then the ticker, and no longer waits for CoinGecko. Ranking (`_pick_best_match`): CEX spot whose description names the coin (MEXC > KuCoin > HTX > Bybit > Binance > ..., same priority as the CEX-pairs path, then TradingView's order) > CEX perpetual (`.P`) > DEX pool on the coin's own chain > **the first listing that names the coin** in TradingView's order (pools only when the coin's chain is unknown or matches; a same-name pool on a chain the coin is known not to be on is never used) > TradingView's `CRYPTO:<coin>USD` index. A same-ticker different coin (SpaceX Inu, Super Intelligence for "SI") is never charted. Results are cached 24h per coin; all cached lookups were cleared on 2026-10-15 so every coin re-resolves with the new search on its next view.
The chart still prefers a symbol built from the coin's own cached CEX market pairs (`_resolve_chart_symbol`); the search result is the fallback, and a hand-picked chart (below) beats both. A perpetual chart's live header price uses its spot pair (`live_prices`: `.P` stripped). Measured locally: Super Inu `MEXC:SIUSDT` about 4s after a cold page load (was: never), 1.7s on the next visit; CyberLeek `KCEX:CYBERLEEKUSDT` about 1s. Tests in `tests/test_price_hub.py`.
</details>

<details><summary>Fix a wrong chart by hand (red report icon, 2026-10-13)</summary>

A gradient "edit" icon (the image supplied 2026-10-15, `assets/chart-edit-icon.png` at 96px shown 20px; it replaced the red warning triangle; `coin_detail.py::_chart_report_button`) sits right after "<Coin> Live Chart" on every coin page. Clicking it (logged in) opens a centered popup (`_chart_picker_dialog`): the chart symbol in use and whether it is automatic or picked by hand; a search of TradingView's own markets for the coin (`chart_override_service.search_options`; since 2026-10-15 **everything TradingView's Crypto tab lists**: spot, perpetuals, DEX pools and TradingView's indexes, labelled CEX / Perp / DEX / Futures / Index with the venue and market type, in TradingView's order with indexes last; it searches the typed text, the coin's name when the text is its ticker, and "<ticker>USDT", because some listings such as BingX's `CYBERLEEKUSDT.P` only appear for the pair name) with a "Use" button per market; a field to type a symbol exactly as on TradingView ("EXCHANGE:SYMBOL", validated); and "Reset to automatic". A choice is saved in Postgres (`chart_symbol_overrides`, keyed by CMC id; migration `d5e8f1a3b7c9`), loaded into the shared coin list when it is built, and checked first by `coin_state._resolve_chart_symbol`, so it applies to every session, survives restarts, reloads and closed tabs, and also drives the 1-second live header price (same pair). Verified: pick -> chart switches at once; a new browser session and a server restart keep it; reset returns to the automatic pick. Re-verified 2026-10-15 with a perpetual: picking `BINGX:CYBERLEEKUSDT.P` switched the chart, was stored in Postgres and was still charted after leaving and reopening the page.
</details>

<details><summary>Alerts and coin information follow the live price (2026-10-14)</summary>

The stored CoinMarketCap price goes stale (frozen while CMC has no credits; wrong for memecoins priced on a DEX: CyberLeek stored $0.00105 vs live $0.00255), and three places used it instead of the price the chart shows. Now:
- **Alert dialog**: "Now: ..." and the prefilled target use the live header price (`CoinState._alert_ref_price`), and the above/below decision is taken against it (a target of $0.002 on CyberLeek is saved as "below", it used to be "above").
- **Alert checkers** price a coin the way its page does: the tab checker (`start_alert_watch`) and the watchlist popup pass the token's contract so the DEX price (`live_prices._dex_price`, DexScreener) is the fallback; the 24/7 server checker (`frontend/alert_watcher.py`) prices EVERY alerted coin from the same chart pair as the page and the TradingView chart (hand-picked symbol, else `_resolve_chart_symbol` over the coin's cached market pairs, read through `live_prices.fetch_live_prices` like the header price), and only if that cannot be priced falls back to the shared exchange price list, the DEX pool by contract, and last the stored price (2026-10-15; test `tests/test_alert_watcher.py`). Verified with no browser open: an "above $0.002" CyberLeek alert fired within ~15s with "now at $0.00256" (it never would have with the stored price).
- **Coin information** (Market cap, Unlocked Mkt Cap, Vol/Mkt Cap, FDV, locked-supply value) is re-based on the live price by `app/services/coin_info.py::scaled_info` (stored figure x live/stored price, i.e. circulating supply x price) from `CoinState._rebase_coin_info`, written only when the price moved >0.5% since the last write (each write re-sends the coin's rows). **Liq/Mkt Cap** (always "—" before) is the token's total DEX liquidity (DexScreener, refreshed every 60s) over the market cap, for coins with a contract. CyberLeek: market cap $769.6K -> $1.87M, Liq/Mkt Cap 33.9%. Volume stays CMC's (it agreed with DexScreener's $1.04M). Coins with no contract keep "—".
</details>


**Instant alert popup (2026-10-15):** "Add New Alert" and an alert's pencil open the price-alert popup at once (about 10 ms) instead of waiting for the server (on the live site the round trip made it lag). The popup is an always-rendered overlay (`coin_detail.py::_alert_dialog`, class `alert-overlay`); `assets/instant_ui.js` (section 3b) shows it on the click of any `.alert-open-btn`, with the title ("New / Edit price alert") and the prefill (the coin's price text for a new alert, the alert's `data-alert-price` for an edit) already in place, and hides it at once on Cancel, the backdrop or Escape. The click's own server event still runs (which alert is edited, `alert_dialog_open`), and the server stays the authority: an error keeps it open, a successful save closes it (`data-open` -> the script drops its flag). **Chart volume:** the volume bars at the bottom of every embedded TradingView chart (coin pages and the five `/tools` charts) are hidden with the widget parameter `hide_volume=1` (`hidevolume` does nothing).

**Coin age (2026-10-15):** the stats list ends with **Age**, e.g. "1 year 47 days (12/10/2025)" (years + days, then the start date as day/month/year; "23 days (…)" under a year; "—" until a source knows it), on every `/coins/<name>` page. Sources, best first (a better one replaces a worse one, never the reverse): CoinGecko `genesis_date` (real start, mostly the larger coins: Bitcoin 03/01/2009, Ethereum 30/07/2015, BNB 08/07/2017) -> CoinMarketCap `date_launched` (its /info metadata: stored by the weekly metadata sync, no extra credits) -> the creation day of the coin's oldest **DEX pair** (DexScreener, only for coins outside the top 500: a top coin's contract is usually a wrapped copy, e.g. XRP) -> CMC `date_added` (when CMC listed it; the daily listings carry it free). CoinGecko and DexScreener are asked **on demand, once per coin, when its page opens** (`CoinState.refresh_launch_date`; a miss is retried after 3 days, a CoinGecko rate limit is not remembered as a miss, and native coins' placeholder `0xeee…` contracts are never searched on a DEX). **CMC has no credits until 1 Nov 2026**, so the two CMC sources fill in after that; until then coins CoinGecko has no genesis date for (Solana, XRP) show "—". Storage: own table `coin_launch_dates` (migration `b3d5f7a9c1e4`; no change to the Reflex mirror), read into every row when the shared coin list is built (`row["launch_date"]`, `row["age_display"]`). Code: `app/services/coin_age_service.py`, tests `tests/test_coin_age.py`. Also fixed: `coingecko_service._get_top_coin_symbol_map` no longer caches a failed (429) fetch for the life of the process.

**Tag groups (2026-10-15):** the Category / Industry / Platform / Self-Reported Tags groups on every coin page show their first **20** tags as pills and a "View more" pill (same look as the homepage's "More Chain"; "View less" folds it back; no search box) when there are more (`coin_detail.py::_tag_group`, `CoinState.tag_groups_open`, reset on each page load). **Category** badges, and **Platform** badges whose "<Chain> Ecosystem" is a narrative, open that narrative's page `/narrative/<slug>` (`row["narrative_tags"]` / `row["platform_tags"]` = `[{name, href}]`, built in `ensure_universe` from the narratives that exist); the two dummy groups have no links.

**Blue tag links (2026-10-15):** a tag badge that opens a narrative page is blue (blue badge, underline and a blue hover), a badge without a page stays gray, so a visitor can tell which badges are links.

**Coin page header tweaks (2026-10-15):** the Age row shows only years and days ("7 years 232 days", "42 days"), no start date (the date is still stored in `coin_launch_dates`). Linked tag badges no longer underline on hover (they just tint blue). **Price header:** from md (1024 px, desktop) the live dot and the 24h change sit **below** the price; on tablets and phones they stay beside it with a little more left spacing (`margin_left 0.5em`); the dot and the change text are vertically centred at every width.

**Alert list split (2026-10-15, labels removed + order changed later that day):** the left-column **Alerts** section separates a coin's alerts into the green "above" group and the red "below" group with a divider between them (shown only when both exist); there are no "Above price" / "Below price" label rows any more (each row's green up / red down arrow shows the side), and both groups list the **highest price first** (`coin_detail.py::_alert_group`, `CoinState.coin_alerts_above` / `coin_alerts_below`); the add / edit / delete controls are unchanged.


<details>
<summary><strong>🔥 Liquidation Heat Map link (2026-10-24)</strong></summary>

Every coin page has a direct link, **Liquidation Heat Map · Coinglass**, in the left column right above the Alerts section (below the "Your MEXC" box for viewers who have one). It opens `https://www.coinglass.com/pro/futures/LiquidationHeatMap?coin=<TICKER>` in a new tab (`CoinState.coinglass_heatmap_url`: the page coin's ticker, upper-cased and URL-encoded; the link is hidden until the coin is known). Code: `coin_detail.py::_heatmap_link`. Coinglass decides what it shows for a ticker it does not list. Tests: `tests/test_coin_links.py`.
</details>
