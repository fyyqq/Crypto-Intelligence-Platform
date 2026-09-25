# Crypto Intelligence Platform - Development Roadmap & Rules

## 🎯 Project Overview
An automated crypto intelligence platform that tracks market data dynamically from CoinMarketCap (CMC), maps assets into fluid narratives based on real-time data, and utilizes AI via OpenRouter to analyze geopolitical and financial news for asset correlation predictions.

## 🏗️ Technical Stack
- **Full-Stack Framework:** Reflex (Python-based modern web framework compiling to Next.js/FastAPI)
- **Database:** SQLite (Managed via Reflex's built-in SQLModel engine)
- **External APIs:** CoinMarketCap Basic (Free Tier), OpenRouter (Claude 3.5 Haiku & Sonnet / DeepSeek-V3), CryptoPanic API / Google News RSS.

## 📜 Development Rules & Workflow Constraints (Strict)
1. **Strictly Modular:** Do not write large monolithic files. Split components into separate files for state handling, UI layouts, and external API services.
2. **Step-by-Step Execution:** Do NOT build multiple features at once. Wait for human review and approval for the current feature before moving to the next.
3. **No Hardcoded Narratives:** All token categorization and narrative grouping must be fetched dynamically from the CoinMarketCap API tags/categories endpoint. 
4. **API Optimization & Cost Control:** 
   - Execute the full CoinMarketCap sync (every coin currently listed on CMC — not a Top-N subset — plus categories and per-coin contracts) strictly once every 24 hours (24H Cron) to check for new coin listings and protect the free tier credit limit.
   - A separate, cheap "hot" sync refreshes just the top N coins' quote (price/market cap/volume/1h/24h/7d) every HOT_SYNC_INTERVAL_HOURS (default 1h, top 500) via a single listings/latest call — see app/scheduler/jobs.py::run_hot_listings_sync. It never re-fetches the full ~8,000-coin universe or touches categories/contracts, so it stays cheap even at hourly cadence.
   - A view-driven live sync refreshes just whichever page a Reflex session is actually looking at (≤500 coins, whatever the current pagination/narrative/chain filter shows) every 60 seconds, plus immediately on every pagination or filter change — see frontend/state/coin_state.py::live_sync_loop and sync_visible_page (cross-imports app.services.market_data_service.MarketDataService.sync_ids). It only ever touches the coins currently on screen, never the full universe, so it stays cheap even at a 1-minute cadence per viewer.
   - Cache all market data locally to minimize API consumption.
5. **Incremental Reflex UI Build:** Every time a backend service or data collection pipeline is nearly complete, immediately build its corresponding Reflex frontend view component. Do not wait until the entire project is finished to build the design.
6. **MCP Workflow Automation (Mandatory):**
   - **GitHub MCP:** Every completed sub-feature/feature change MUST be automatically staged, committed, and pushed to the GitHub repository using the GitHub MCP tool before asking for the next review.
   - **Notion MCP:** Upon final human confirmation of a feature/sprint completion, the AI must connect via Notion MCP to update the project management board (e.g., updating Sprint status, moving tasks to "Done").

## 🗺️ Feature Roadmap (Iterative Build Plan)

### 📌 Feature 1: Dynamic Market Data Sync & Dashboard
- **Backend Service:** ✅ Implemented three-tier sync architecture:
  - 24-hour full-universe sync: all CMC-listed coins, categories, and contracts via `app/scheduler/jobs.py::run_market_data_sync`.
  - 1-hour hot sync: top 500 coins' quotes (price, market cap, volume, % changes) via `run_hot_listings_sync` — cheap single API call.
  - 60-second view-driven live sync: only coins on current page/filter, refreshes every minute + immediately on filter/pagination. `frontend/frontend/state/coin_state.py::live_sync_loop` / `sync_visible_page`.
  - All cached locally via SQLite/SQLModel. Scheduled in `start_scheduler()`.
- **Frontend (Reflex UI):** ✅ Complete responsive dark-mode interactive dashboard (320px–1728px+):
  - Data table: sortable columns, market-cap-ranked, 24h/7d trend cells. All 10 columns always visible with horizontal scroll fallback.
  - Sticky header: position:sticky cells with proper height stretching to prevent gaps.
  - Pagination: 50/100/200/500 rows per page, arrow controls, responsive padding.
  - Dynamic pill filters: top-10-by-count narrative pills + top-20-by-count chain pills (AND-combined), refreshed on each sync, wrapped layout on mobile/tablet.
  - Real-time search: name/ticker queries all coins, debounced 300ms. Icon-triggered on desktop, always-visible full-width field on mobile (<768px).
  - Skeleton loading: visible ~150–250ms on filter/search/pagination via async gate.
  - Responsive layout: centered/stacked mobile/tablet (<1280px), left-aligned desktop (≥1280px). Footer, sliders, search all optimized per width.
  - Alert card badges: flex-wrap prevents overlap. Table surface styling removed below 1280px.
- STATUS: ✅ COMPLETE (verified 2026-09-24: zero console errors, zero network failures, all responsive breakpoints tested)

### 📌 Feature 2: Knowledge Base & AI Business Model Agent
- **Backend Service:** Build a background worker to fetch whitepapers/documentation for the Top 500 cached coins. Use OpenRouter (Claude 3.5 Sonnet) to extract the business model and summary.
- **Frontend (Reflex UI):** Add an interactive side-drawer or modern modal component that activates when a coin is clicked, displaying the AI-generated business model breakdown.
- STATUS: 🔒 LOCKED

### 📌 Feature 3: Social & Developer Metrics Tracker
- **Backend Service:** Connect to GitHub API and X/LunarCrush API to monitor developer activities and social media volume.
- **Frontend (Reflex UI):** Add clean responsive chart components showing the correlation between social spikes, code commits, and asset price movements.
- STATUS: 🔒 LOCKED

### 📌 Feature 4: Financial News Ingestion Pipeline
- **Backend Service:** Build an aggregator for Google News RSS and CryptoPanic free API. Use OpenRouter (Claude 3.5 Haiku or DeepSeek-V3) to classify news into specific Narratives and Types (Rumour vs. Actual Happen).
- **Frontend (Reflex UI):** Create a beautiful responsive feed grid showing categorized news cards, color-coded based on the AI's classification (e.g., alert borders for rumours vs. verified events).
- STATUS: 🔒 LOCKED

### 📌 Feature 5: Automated "Why Pump" Engine
- **Backend Service:** Set a database trigger to flag when a local cached coin price spikes >15%. Instruct OpenRouter to cross-reference breaking news with the pre-stored business model to generate a report.
- **Frontend (Reflex UI):** Add a dedicated "Market Alpha Reports" dashboard tab that populates automated markdown component layout cards explaining market pumps.
- STATUS: 🔒 LOCKED

### 📌 Feature 6: Narrative Beta Correlation Engine
- **Backend Service:** Implement an algorithm to structure large-cap market leaders (Main Native Coins) vs. small-cap alternatives inside the same dynamic CMC narrative category.
- **Frontend (Reflex UI):** Integrate real-time toast notification banners and a visual correlation matrix pointing out laggard assets in surging narratives.
- STATUS: 🔒 LOCKED
