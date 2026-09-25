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

### 🔧 Current State
- Reflex server running in prod mode (`reflex run --env prod --single-port`) on port 3000, restarted this session to pick up the TradingView fix above (this restart's own build — anyone else's local server needs the same restart to pick this up).
- **Git note:** the working directory is now an actual local git repo (`git init` happened at some point this session lineage — `Is a git repository` flipped `false` → `true`), tracking `origin/main` = `fyyqq/Crypto-Intelligence-Platform`. However, all commits so far have been pushed directly via the **GitHub MCP tool's `push_files`** (a direct-to-remote-API call), which does **not** update the local git index/working tree state — so `git status` locally still shows the already-pushed files (`app/models/coin.py`, `app/services/market_pairs_service.py`, `frontend/frontend/components/coin_detail.py`, `frontend/frontend/frontend.py`, `frontend/frontend/state/coin_state.py`) as modified/untracked even though they match `origin/main` exactly. Don't `git pull`/`git reset` to "fix" this without checking `git diff` against `origin/main` first — the local tree is stale relative to git's bookkeeping, not the remote.
- **All Feature 2 work-so-far is pushed to `origin/main`** across 6 commits this session: category-badge fallback + CEX/DEX-only Markets tabs (`coin_state.py`/`coin_detail.py`), top-15 CEX/DEX + USDC exclusion + Binance Alpha (`market_pairs_service.py`), About-section AI fallback (`description_ai_service.py` + `Coin.description_ai_generated_at` migration `b1d0fd86c529`), dynamic page title (`coin_state.py`/`frontend.py`).
- Postgres migration `b1d0fd86c529` (description_ai_generated_at) applied to the local dev Postgres DB via `alembic upgrade head`. **Not yet confirmed applied to any other environment** — if this is deployed anywhere besides this dev machine, run `alembic upgrade head` there too before the app boots against that DB.
- `ai-instructions.md` has an uncommitted local addition (rule 7, AI Memory & Handoff Automation) — pre-existing from before this session, unrelated to Feature 2, left as-is.

### ➡️ Next Steps
1. **Human review/sign-off needed before continuing** per rule 2 — Feature 2 has real, verified functionality (business summaries, category badges, About-section AI fallback, real Markets data) but does NOT yet match `ai-instructions.md`'s literal Feature 2 spec on two points: no scheduled background worker (everything is on-demand/page-view-triggered), and no side-drawer/modal (built inline into the existing page instead). Decide: (a) accept the inline/on-demand architecture as the real Feature 2 design and update `ai-instructions.md`'s spec to match reality, or (b) build the literal spec's missing pieces.
2. **If (b) — the next concrete code block to write** is a scheduled batch job mirroring the existing hot-sync pattern, e.g.:
   ```python
   # app/scheduler/jobs.py
   def run_business_summary_batch_sync():
       """Daily job: proactively generates business_summary + upgrades
       description for the Top 500 cached coins (by cmc_rank), so an
       unvisited coin already has real content instead of waiting for
       its first page view. Mirrors run_hot_listings_sync's top-500 scope
       and cost-control spirit (rule 4)."""
       db = SessionLocal()
       try:
           coins = db.scalars(
               select(Coin).where(Coin.cmc_rank <= 500).order_by(Coin.cmc_rank)
           ).all()
           for coin in coins:
               upgrade_description(db, coin)
               generate_description_from_sources(db, coin)
               get_business_summary(db, coin)
       finally:
           db.close()
   ```
   Then register it in `start_scheduler()` next to `run_hot_listings_sync`, on a daily interval (business_summary_ttl_days is 60d, so daily just catches newly-top-500 coins, not re-generation churn) — and mirror the touched coins into Reflex's SQLite cache the same way `reflex_cache_service.sync_reflex_cache()` already does for the full nightly sync.
3. Once 1–2 are resolved (or explicitly deferred by the user), update `ai-instructions.md`'s Feature 2 STATUS from `🔒 LOCKED` to `⏳ IN PROGRESS` (currently still shows LOCKED even though real work has shipped) so both files agree.
