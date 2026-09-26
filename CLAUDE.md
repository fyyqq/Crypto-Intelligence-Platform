# Claude Code Project Rules

## 🤖 Handoff & Session Limit Rule
* **Mandatory Action:** AFTER completing any significant change, sub-task, or bug fix, you MUST immediately rewrite and update the sections below (`### 🔧 Current State` and `### ➡️ Next Steps`) inside this file.
* **Why:** This ensures that if the terminal session suddenly runs out of API limits, the current progress state is perfectly preserved right here, allowing a seamless handoff to GitHub Copilot inside VS Code without losing data.


---

## Playwright Testing Rules

When asked to run, write, or execute Playwright tests against web pages loaded in the VS Code context:
- **Never open external Chrome windows or tabs.** All browser actions must be completely hidden.
- **Utilize the Context Picker Panel:** Use the DOM structure, selectors, and context provided by the active VS Code Context Picker panel for selecting elements.
- **Headless Execution Only:** Execute all test runs or interactions headlessly in the background. Use either:
  1. The installed Playwright MCP server tools (`playwright_navigate`, `playwright_click`, etc.) which run entirely in the background.
  2. The integrated terminal via `npx playwright test --headless`.
- **Provide Results in Chat:** Print the execution outcome, assertion results, or console errors directly back into the chat interface without creating visual browser popups.

---

## Commit & Push Rule
* **Mandatory Action:** After completing and verifying any change, sub-task, bug fix, or feature — not batched until end of session — immediately `git add`/`git commit`/`git push` to `origin/main` (a normal local commit + push, not the GitHub MCP `push_files` workaround, unless local git is unavailable).
* **Why:** Keeps `origin/main` current for handoff to GitHub Copilot or another session at any moment, and avoids losing verified work if the session ends unexpectedly.
* **How to apply:** Commit message should summarize the "why" of the change in 1-2 sentences. Update the `### 🔧 Current State` / `### ➡️ Next Steps` sections (per the Handoff rule above) in the same commit when relevant.

---


## Crypto Intelligence Platform — Session State Summary

### ✅ Feature 1: Dynamic Market Data Sync & Dashboard — COMPLETE
**Backend Implementation:**
- **Sync architecture** (rule 4 in `ai-instructions.md`): Three-tier sync strategy optimized for cost and freshness:
  - **24h full-universe sync** (`app/scheduler/jobs.py::run_market_data_sync`): All CMC-listed coins, categories, and per-coin contract data — runs once daily to detect new listings while protecting free-tier credits.
  - **1h hot sync** (`run_hot_listings_sync`): Top 500 coins' quotes (price, mcap, volume, % changes) via single API call — cheap/hourly.
  - **60s view-driven live sync** (`frontend/frontend/state/coin_state.py::live_sync_loop` / `sync_visible_page`): Only coins currently on-screen, refreshes every minute + immediately on filter/pagination changes. Cross-imports `app.services.market_data_service.MarketDataService.sync_ids` for minimal API footprint.
  - All three scheduled in `start_scheduler()`.

**Frontend (Responsive Design 320px–1728px+):**
- **Data table**: dark-mode, sortable columns, market-cap-ranked, 24h/7d trend sparkline cells. All 10 columns always visible; horizontal scroll (`.coin-table-scroll-fix` overflow-x) is fallback when table width exceeds available space.
- **Sticky header**: position:sticky header cells with `height: 100%` to prevent gaps when labels wrap across rows.
- **Pagination**: 50/100/200/500 rows per page, page-window arrow controls. Responsive padding adjusts for mobile.
- **Dynamic pill filters**: Top-10-by-count narrative pills + top-20-by-count chain pills (AND-combined), computed fresh on each sync (not hardcoded). Wrapped layout in sidebar (no slider at tablet/mobile widths). `CoinState.categories` / `CoinState.chains`.
- **Real-time search**: Name/ticker search queries all coins (not just current page), debounced 300ms. Desktop: icon-triggered popover. Mobile (<768px): always-visible full-width field in its own row below heading.
- **Skeleton loading**: Genuinely visible (~150–250ms) on every filter/search/pagination change via async gate (`asyncio.sleep(0.25)` in state handlers).
- **Alert & news sliders**: Horizontal drag-scroll with arrow buttons at all viewport widths. Alert card badges wrap to prevent overlap on narrow widths.
- **Footer**: Centered/stacked on mobile/tablet (<1280px), left-aligned two-column layout on desktop (≥1280px).
- **Table surface styling**: Border/background/backdrop-blur stripped below 1280px (tablet/mobile), preserved on desktop for visual hierarchy.

**UI Polish & Fixes (2026-09-24 session):**
- Header white gap fix: Added `height: 100%` to sticky header cells to restore auto-stretch behavior when wrapped labels make rows taller than single-line cells.
- Table surface variant cleanup: Removed Radix "surface" border/backdrop-blur on mobile/tablet, keeping card look only at desktop widths.
- Footer centering extended: Navbar and copyright row stay centered through 1279px, only split to desktop layout at 1280px+.
- Mobile search bar redesign: Magnifying glass icon hidden <768px, replaced with always-visible full-width field in dedicated row.
- Alert card badge wrap: Added `flex-wrap: wrap` to prevent "REAL-WORLD ASSETS (RWA)" + "ONDO" overflow; widened narrowest card breakpoints (270px/290px) for breathing room.
- Search bar spacing: Added top margin to mobile search field for visual separation from header row.

**Verified 2026-09-24:**
- Live QA pass: narrative pill filtering, chain pill filtering, rows-per-page toggle, pagination arrows, search (open/type/clear), responsive layout at 6+ viewport widths (320/375/480/768/1024/1280/1366/1440/1728px).
- Zero console errors, zero failed network requests, zero page-level horizontal overflow at any width.

### ⏳ Feature 2: Knowledge Base & AI Business Model Agent — IN PROGRESS
**Backend Implementation:**
- **AI business summary** (`app/services/business_summary_service.py::get_business_summary`): On-demand OpenRouter call (`nvidia/nemotron-3-ultra-550b-a55b:free`, NOT Claude 3.5 Sonnet as originally scoped in `ai-instructions.md` — that model is retired from OpenRouter, and this project's OpenRouter account is $0-balance free-tier, which 402s on any paid model regardless of price; see `settings.openrouter_model` comment). Prompts for a leading `CATEGORY: <label>` line (parsed via `_CATEGORY_LINE` regex, e.g. "Tokenized Securities Lending Protocol") plus 2-3 `TITLE: <heading>` paragraphs. Gated by `Coin.business_summary_updated_at` + `settings.business_summary_ttl_days` (60d default) — periodic, not one-time, since a project's real business model can drift.
- **About-section real-description upgrade, two independent one-time steps** (`frontend/frontend/state/coin_state.py::_fetch_better_description`, called from `CoinState.refresh_coin_description`):
  1. `app/services/coingecko_service.py::upgrade_description` — CoinGecko `/coins/{platform_id}/contract/{address}` contract-address lookup for a real curated project write-up, replacing CMC's auto-generated "`<name>` is a cryptocurrency and operates on..." boilerplate (detected via `is_boilerplate_description`'s 3-marker fingerprint). Gated once-ever by `Coin.description_synced_at`.
  2. `app/services/description_ai_service.py::generate_description_from_sources` — if STILL boilerplate after step 1 (typical for memecoins/newly-listed tokens with no whitepaper anywhere, e.g. Dogecoin, STONK, Pons confirmed live), generates a grounded AI paragraph from the coin's own website text (`_fetch_website_text`, HTML-stripped via `_TAG_STRIP_RE`/`_ANY_TAG_RE`, capped at `_MAX_WEBSITE_CHARS = 4000`) and/or up to `_MAX_TWEETS = 8` already-cached X posts (`coin.cached_tweets`, reused from `social_service.py`, not re-scraped). System prompt explicitly forbids inventing business model/tokenomics/team details not in the source text. Gated once-ever by `Coin.description_ai_generated_at` (independent of `description_synced_at`).
- **Real CEX/DEX market pairs** (`app/services/market_pairs_service.py::get_market_pairs`): CMC's own `/v2/cryptocurrency/market-pairs/latest` 403s on this project's Basic/free CMC key (error_code 1006 — needs paid tier), so this uses CoinGecko's free `/coins/{id}?tickers=true` instead, reusing `coingecko_service`'s contract-address / top-500-symbol-map coin-id resolution.
  - CEX rows: filtered to `_CEX_ALLOWED_NAMES` (CMC's real top-15 spot-exchange ranking from coinmarketcap.com/rankings/exchanges/, plus "Binance Alpha" per explicit request — flagged as a no-op today since CoinGecko's own `/exchanges/list` has no such distinct tracked entity). USDC-quoted pairs dropped via `_EXCLUDED_CEX_QUOTES` whenever a non-USDC pair exists from the same exchange pool, falling back to keeping USDC only if that would empty the tab.
  - DEX rows: filtered to `_DEX_ALLOWED_BY_CHAIN[chain_name]` — top-15-per-chain real rankings from coingecko.com/en/exchanges/decentralized/`<chain>`, individually curated for Solana/Ethereum/BNB Smart Chain (BEP20)/Base/Arbitrum/Polygon (keyed by `CoinContract.platform_name`, same spelling as `coingecko_service._CHAIN_TO_COINGECKO_PLATFORM`); any other chain falls back to `_DEX_ALLOWED_FALLBACK` (CoinGecko's cross-chain top-15). `_NATIVE_ASSET_CHAINS` maps a native/root asset (ETH, SOL, BNB, MATIC/POL, AVAX — no `CoinContract` row of its own) to its own chain's ranking.
  - Both sides capped to 15 rows (`[:15]`), sorted by `volume_24h` desc, never padded if fewer real listings exist. Gated by `Coin.market_pairs_updated_at` + `settings.market_pairs_cache_ttl_hours` (1h default — far shorter than the description/summary TTLs since exchange volume goes stale fast).
- **New Postgres columns** (`app/models/coin.py`, migration `b1d0fd86c529`): `business_summary`, `business_summary_updated_at`, `business_summary_model`, `business_model_category`, `description_ai_generated_at`, `cached_market_pairs`, `market_pairs_updated_at`.
- **No scheduled batch worker yet** — every step above is on-demand, triggered only by a page visit (`frontend/frontend/frontend.py`'s `/coin/[symbol]` `on_load` list: `CoinState.refresh_coin_description`, `refresh_business_summary`, `refresh_market_pairs`, each a `@rx.event(background=True)`). This deviates from `ai-instructions.md`'s literal Feature 2 spec ("background worker to fetch whitepapers/documentation for the Top 500 cached coins") — nothing in `app/scheduler/jobs.py` proactively generates these yet, so an unvisited coin has no AI summary/description upgrade until someone opens its page.

**Frontend (inline in the existing coin_detail page — no new side-drawer/modal; also a deviation from `ai-instructions.md`'s literal spec, which asked for a modal/drawer triggered on coin click):**
- **Category badge** (`frontend/frontend/components/coin_detail.py::_chart_column`): next to the "`<Coin>` Live Chart" heading, `justify="between"` row. Reads `coin["category_badge_display"]` / `coin["has_category_badge_display"]` (computed in `CoinState._build_row` and patched live in `refresh_business_summary`) — falls back to the coin's real CMC `primary_narrative` tag when no AI category has been generated yet (confirmed live: Ethereum shows "Layer 1"), so every coin's page shows *some* badge instead of an empty gap. Style: `variant="surface"`, `radius="full"`, `style={"border": "1px solid royalblue", "color": "white", "background": "royalblue"}` — solid, no pulse animation (glow removed per explicit request).
- **About section** (`_about_section`): unchanged structural home for both the CoinGecko-upgraded and AI-inferred descriptions — `coin["description_tokens"]` (keyword-highlighted via `_render_highlight_token`/`_tokenize_highlights` in `coin_state.py`), fixed `_ABOUT_COLLAPSED_HEIGHT = "320px"` collapse/expand via `CoinState.about_expanded` + `toggle_about_expanded`, auto-hides the expand arrow for short text via `_about_collapse_fix_script`.
- **AI Summarizations section** (`_business_summary_section`): heading row (`rx.heading("AI Summarizations")` + sparkles icon) matching `_about_section`'s style, per-paragraph blocks via `_business_summary_section_block` (optional `TITLE:` heading + `_highlighted_paragraph(..., color="white")`), bottom credit row (`"Generated by AI"` left, brand-icon + model-name badge right via `_ai_provider_icon`/`CoinState._format_model_badge`). Card style: `border="2px solid royalblue"`, reduced `box_shadow="0 0 10px 1px var(--indigo-a4)"` (glow removed per explicit request, border does the visual work now).
- **Markets section** (`_market_pairs_section` / `_market_pairs_filter_button` / `_market_pair_row`): CEX/DEX-only tabs (`_market_pairs_filter_button("CEX", "cex")`, `("DEX", "dex")` — no "All" tab, removed per explicit request), driven by `CoinState.market_pairs_filter` (default `"cex"`) and `CoinState.filtered_market_pairs` computed var. Table columns: `#`, `Exchange` (icon + name + CEX/DEX `rx.badge`), `Pair`, `Price`, `24h Volume`, `Volume %`, `Last Updated`. Lives inside the same responsive middle chart column as the rest of `_chart_column()` — no new breakpoints; reuses `_CHART_HEIGHTS = ["420px", "480px", "520px", "560px", "600px"]`'s column and `rx.breakpoints(initial="column", lg="row")` from `coin_detail_page()`.
- **Dynamic page title** (`CoinState.page_title` computed var, wired into `frontend/frontend/frontend.py`'s `app.add_page(coin_detail, ..., title=CoinState.page_title)`): browser tab / meta title is `"Repace — <Coin Name>"` (e.g. "Repace — Fartcoin", "Repace — Dogecoin") — the coin's real name, never its ticker, per explicit request. Falls back to `"Repace — Coin Detail"` before `all_coins` has loaded.

**Verified live 2026-09-26 (Playwright, zero console errors on every check):**
- Category badge fallback: Ethereum ("Layer 1"), Ondo (real AI category "Tokenized Securities Lending Protocol").
- About-section AI fallback: Dogecoin (dogecoin.com-sourced 4-sentence real description replacing CMC boilerplate), STONK/stonkfun.xyz (real onchain-coin-platform description). Pons correctly left untouched (declared website domain is dead/NXDOMAIN, zero cached X posts — nothing to ground a description in; attempt still marked so it isn't retried forever).
- Markets top-15 + USDC exclusion: Fartcoin's CEX table dropped Kraken/KuCoin/MEXC's USDC rows in favor of those same exchanges' real USDT/USD/EUR pairs; Fartcoin's DEX table shows a full 15 real Solana-DEX rows; Tether's CEX table dropped BTCC entirely (not in CMC's real top-15) in favor of MEXC/Bybit/OKX/Gate/HTX.
- Dynamic title: confirmed "Repace — Fartcoin", "Repace — Dogecoin", "Repace — STONK (stonkfun.xyz)" on their respective pages.

### 🔧 Bug fix: TradingView chart reload / timeframe reset (2026-09-26 session)
User-reported: the coin-detail page's TradingView chart kept reloading on its own, and the interval kept snapping back to a hardcoded weekly ("W") candle view — any timeframe the viewer picked manually didn't stick.

**Root cause, confirmed live with a MutationObserver** (`frontend/frontend/components/coin_detail.py::_chart_column`): the chart iframe was built via `rx.html(f'<iframe src="{...}">...')` — a raw HTML string handed to React's `dangerouslySetInnerHTML`, not a real typed component. `CoinState`'s single React context re-renders every consumer whenever *any* field changes, and `all_coins` gets reassigned roughly every 60s by `detail_sync_loop` (plus once each by the four on-load background refreshers). Confirmed empirically (childList mutations logged every ~60–62s, `added:1, removed:1` on the iframe node) that this tore down and rebuilt the iframe on every one of those updates — even when the resulting HTML string was byte-for-byte identical — because `dangerouslySetInnerHTML` reassignment vs. a real DOM-diffed prop doesn't get the same "skip if unchanged" treatment here. Each rebuild reset TradingView's own in-widget state (the viewer's manually chosen interval) back to whatever was hardcoded.

**Fix**, both in `coin_detail.py` and `coin_state.py`:
1. `_chart_column()`: replaced the `rx.html(f'<iframe ...>')` string with a real `rx.el.iframe(src=rx.color_mode_cond(...), custom_attrs={"allowtransparency": "true", "frameborder": "0"}, style={...})` — a genuine typed React prop. The surrounding component can still re-render on every state update; React's reconciler now only touches the `src` attribute when its value actually changes, so the iframe (and the viewer's chosen timeframe) survives background syncs.
2. `CoinState._tradingview_iframe_src`: symbol is now read from `self.symbol` (the static `/coin/[symbol]` route param) instead of `self.selected_coin.get("symbol")`, removing an unnecessary dependency on `all_coins` at the value-computation level too (belt-and-suspenders with fix #1).
3. Default `interval` changed from `"W"` (weekly) to `"60"` (1 hour) per explicit request, `range="ALL"` kept so the chart still opens fully zoomed out to the coin's whole listing history on every page load/reload — just at hourly candle granularity instead of weekly. Viewers can still change the interval afterward via TradingView's own UI, and — per fix #1 — it now actually stays changed.

**Verified live (Playwright + MutationObserver + performance/network APIs, Bitcoin's page)**: before the fix, the iframe's parent node saw a childList mutation (remove+re-add) roughly every 60–62s, matching `detail_sync_loop`'s cadence. After the fix, across a 75-second window spanning a full sync tick, zero mutations, zero additional `widgetembed` network requests, and `iframe.addEventListener('load', ...)` fired zero additional times — same DOM node throughout (`iframe === <original reference>` stayed `true`).

### 🔧 Bug fix: TradingView chart wrong/missing symbol + sub-$1 price truncation (2026-09-26 session)
User-reported: several coin pages' chart showed TradingView's "This symbol doesn't exist" error instead of a real chart (e.g. `/coin/zkml`, and intermittently `/coin/btw`, `/coin/shib`); the chart's timeframe also looked "locked" to a weekly/monthly view regardless of the app's own hourly default. Separately, coins priced under a cent (e.g. SHIB, real price `$0.000005887`) showed a flat `$0.00` everywhere a price is displayed.

**Root causes found (four distinct bugs, all in the same chart-symbol code path):**
1. **`range="ALL"` silently overrides `interval`** — confirmed live against TradingView's own widgetembed: passing both `range="ALL"` and `interval="60"` makes TradingView pick its own coarser candle size (month) for the full-history zoom, ignoring the requested interval entirely. This was the real cause of the "locked timeframe" symptom, not anything cache/state-related.
2. **Bare, unprefixed `"{SYMBOL}USDT"` guessing is unreliable** — TradingView doesn't reliably resolve an unprefixed symbol to the right venue for smaller-but-real listings (MEXC/Gate/HTX/...), and worse, can silently latch onto a completely different, malformed symbol (confirmed live: a bare `SHIBUSDT` query resolved to `KUCOIN:SHIBA INUUSDT`, which doesn't exist).
3. **CoinGecko's own per-ticker `base` field can be the coin's full name, not its ticker** — confirmed live for Shiba Inu's own KuCoin listing (`base: "SHIBA INU"`, not `"SHIB"`). `market_pairs_service.py`'s `_display_symbol` was also applying its DEX-only "raw base is a contract address, use the CoinGecko id instead" correction to CEX pairs too, compounding this.
4. **`_fmt_usd` always rounded to 2 decimals** — anything under a cent rounds straight to `$0.00`, hiding the coin's real price entirely.

**Fixes, across `app/services/market_pairs_service.py`, `frontend/frontend/state/coin_state.py`, `frontend/frontend/components/coin_detail.py`:**
1. Dropped the `range` param entirely — `interval="60"` (1h) is now actually honored on every load.
2. New `CoinState._resolve_tradingview_symbol()`: picks a real, exchange-prefixed symbol (e.g. `BITGET:BTWUSDT`) from this coin's own already-fetched CEX market pairs (`_TRADINGVIEW_EXCHANGE_PREFIXES` maps `market_pairs_service`'s real exchange names to TradingView's own prefixes), ranked by that pair's real 24h volume. Returns `None` — never a bare guess — when no real CEX pair resolves.
3. The symbol's **base** always comes from the coin's own known ticker (`self.symbol`), not the pair's own `market_pair` base string (fixes the "SHIBA INU" case structurally, not just for that one coin); the **quote** is validated against a plain `[A-Z0-9]{2,10}` pattern before use.
4. `market_pairs_service._display_symbol`/`_normalize` now only apply the CoinGecko-id-derived name substitution to DEX pairs (`is_dex=True`); CEX pairs always use their own raw ticker.
5. New three-state chart UI (`_chart_column`/`_chart_placeholder` in `coin_detail.py`, `has_tradingview_chart`/`tradingview_chart_pending` in `coin_state.py`): real iframe when a symbol resolves, a "Loading chart…" placeholder while this coin's market-pairs fetch is still in flight, a plain "No live chart available for this coin" message once it's confirmed (via the new `market_pairs_fetched` row flag) that this coin genuinely has no real exchange listing (e.g. DEX-only microcaps like zKML) — never TradingView's own broken-looking error card.
6. Found and fixed a **separate, pre-existing cache-sync bug** while wiring up `market_pairs_fetched`: `CoinState._fetch_market_pairs`'s reflex-sqlite mirror wrote `cached_market_pairs` back but never `market_pairs_updated_at`, so the Reflex-side "has this been fetched" check was permanently `False` even long after Postgres had a real cached result. Now mirrors both fields.
7. `_fmt_usd` (shared by the big price header, homepage table, and Markets pair rows) now shows up to 8 decimals for sub-$1 prices instead of a fixed 2, e.g. SHIB now shows `$0.0000059` instead of `$0.00`. $1+ prices are unaffected.
8. Markets section CEX/DEX tabs: new `CoinState.effective_market_pairs_filter` auto-switches to whichever side (CEX/DEX) actually has real listings when the other is empty — a DEX-only coin like zKML now opens on the DEX tab instead of an empty CEX table.

**Verified live (Playwright, multiple coins after each fix + full server restart to reload backend Python)**: BTW now resolves to `BITGET:BTWUSDT` with real OHLC data and a live "Market open" status; SHIB resolves to `KUCOIN:SHIBUSDT` (was `KUCOIN:SHIBA INUUSDT`, invalid) and its price now reads `$0.0000059`; zKML (confirmed via TradingView's own symbol-search API to have zero real listings anywhere) now shows the clean "no chart" placeholder instead of an error card.

**Known external limitation, not a bug in this app**: while testing, TradingView's own widgetembed occasionally returned empty OHLC (`∅`) even for a confirmed-valid symbol in a fresh, non-embedded tab — this is transient flakiness/rate-limiting on TradingView's side from rapid repeated test requests, unrelated to the code above.

### 🔧 Follow-up: chart clock set to Kuala Lumpur time (2026-09-26 session, same day)
Per explicit request, every coin page's TradingView chart now displays its own bottom-right clock in Kuala Lumpur time instead of TradingView's UTC default. Single-line change: `CoinState._tradingview_iframe_src`'s widget `params` now includes `"timezone": "Asia/Kuala_Lumpur"` (Singapore, `"Asia/Singapore"`, is the noted fallback — same UTC+8 offset — if Kuala Lumpur is ever dropped from TradingView's supported IANA list). Since both light/dark iframe src vars share this one function, this applies to every `/coin/[symbol]` page with zero per-page changes. Verified live on `/coin/btw`: clock read `"04:51:55 UTC+8"`.

Also created `.vscode/mcp.json` this session (Notion MCP server config, `https://mcp.notion.com/mcp`) at the user's request — **not yet authorized**: VS Code's MCP OAuth flow is interactive and was left for the user to complete (Command Palette → **MCP: List Servers** → start `notion` → approve in browser). Unrelated to Feature 2 functionality, just sitting in the repo as workspace config.

### 🔧 Current State
- **Reflex server is NOT currently running** — the terminal running `reflex run --env prod --single-port` on port 3000 exited/was killed at the end of this session (last known-good restart did include every fix below). Whoever picks this up next needs to start it fresh:
  ```bash
  source .venv/bin/activate && cd frontend && reflex run --env prod --single-port
  ```
  (prod mode does not hot-reload Python — restart the whole process after any further state/service change, only the frontend JS build hot-swaps.)
- **Everything from this session is committed and pushed to `origin/main`** (plain `git`, not the GitHub MCP `push_files` workaround) — working tree is clean as of the last commit:
  - `df9786a` — TradingView chart wrong/missing symbol fix + sub-$1 price truncation fix + CEX/DEX auto-select tab (see bug-fix section above for full detail).
  - `aa91bf2` — Kuala Lumpur chart timezone + `.vscode/mcp.json` (Notion MCP config, unauthorized).
- No DB migrations pending — nothing this session touched the schema (`market_pairs_fetched` reads the existing `coin.market_pairs_updated_at` column; the timezone/MCP changes are pure config/frontend).
- Test-data note (should already be a no-op by now): `market_pairs_updated_at` was manually cleared then restored for BTW/PONS/CRO/FARTCOIN/ZKML in the local dev Postgres DB while debugging the chart-symbol fix — no lasting effect, just forced those 5 coins to re-sync once instead of waiting out the 1h TTL.

### ➡️ Next Steps
1. **Restart the Reflex server** (see command above) before doing anything else — nothing is currently listening on port 3000.
2. **Complete Notion MCP authorization**, if Notion access is actually wanted for this project: open the Command Palette → **MCP: List Servers** → start `notion` → approve the OAuth prompt in the browser for the workspace containing "Crypto Intelligence Platform". Until this is done, `.vscode/mcp.json` is inert config with no effect.
3. **Feature 2 architecture decision still open** (carried over across multiple sessions now, still not touched): Feature 2 has real, verified functionality but does NOT yet match `ai-instructions.md`'s literal spec on two points — no scheduled background worker (everything is on-demand/page-view-triggered), and no side-drawer/modal (built inline into the existing page instead). Still needs a decision: (a) accept the inline/on-demand architecture as the real design and update `ai-instructions.md`'s spec to match reality, or (b) build the literal spec's missing pieces (see the `run_business_summary_batch_sync` sketch a few sections up, still unimplemented).
4. Once 3 is resolved (or explicitly deferred), update `ai-instructions.md`'s Feature 2 STATUS from `🔒 LOCKED` to `⏳ IN PROGRESS` so both files agree.
5. Consider applying the same "never guess a bare exchange symbol" pattern to any other place in this codebase that might construct a TradingView/exchange symbol from raw ticker data — the chart-symbol fix this session only touched the coin-detail chart, but the same CoinGecko base/target data quirk (fixed in `market_pairs_service.py`) could resurface anywhere else that reads `market_pair` directly instead of the coin's own known symbol.


