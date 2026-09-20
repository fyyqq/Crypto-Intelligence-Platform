# Crypto Intelligence Platform - Development Roadmap & Rules

## 🎯 Project Overview
An automated crypto intelligence platform that tracks market data dynamically from CoinMarketCap (CMC), maps assets into fluid narratives based on real-time data, and utilizes AI via OpenRouter to analyze geopolitical and financial news for asset correlation predictions.

## 🏗️ Technical Stack
- **Backend:** Python (FastAPI)
- **Frontend UI:** Streamlit (Python-based data dashboard)
- **Database:** PostgreSQL (with Prisma ORM) OR MongoDB
- **External APIs:** CoinMarketCap Basic (Free Tier), OpenRouter (Claude 3.5 Haiku & Sonnet / DeepSeek-V3), CryptoPanic API / Google News RSS.

## 📜 Development Rules & Workflow Constraints (Strict)
1. **Strictly Modular:** Do not write large monolithic files. Split services into controllers, routes, models, and external API wrappers.
2. **Step-by-Step Execution:** Do NOT build multiple features at once. Wait for human review and approval for the current feature before moving to the next.
3. **No Hardcoded Narratives:** All token categorization and narrative grouping must be fetched dynamically from the CoinMarketCap API tags/categories endpoint. 
4. **API Optimization & Cost Control:** 
   - Execute the CoinMarketCap sync strictly once every 24 hours (24H Cron) to check for new coin listings and protect the free tier credit limit.
   - Cache all market data locally to minimize API consumption.
5. **Incremental Frontend UI (Streamlit):** Every time a backend feature or data collection pipeline is nearly complete, immediately build its corresponding Streamlit UI component/view. Do not wait until the entire project is finished to build the design.
6. **MCP Workflow Automation (Mandatory):**
   - **GitHub MCP:** Every completed sub-feature/feature change MUST be automatically staged, committed, and pushed to the GitHub repository using the GitHub MCP tool before asking for the next review.
   - **Notion MCP:** Upon final human confirmation of a feature/sprint completion, the AI must connect via Notion MCP to update the project management board (e.g., updating Sprint status, moving tasks to "Done").

## 🗺️ Feature Roadmap (Iterative Build Plan)

### 📌 Feature 1: Dynamic Market Data Sync & Dashboard (Current Focus)
- **Backend:** Build a scheduler that runs strictly once every 24 hours (24H Cron) using CoinMarketCap Basic Free API to fetch the Top 500 coins and dynamic tags/categories. Save data into the local database cache.
- **Frontend (Streamlit):** Build a basic clean table view to display the live Top 500 coins and a dropdown/filter to group them dynamically by their CoinMarketCap narratives.
- STATUS: ⏳ IN PROGRESS

### 📌 Feature 2: Knowledge Base & AI Business Model Agent
- **Backend:** Build a background worker to fetch whitepapers/documentation for the Top 500 cached coins. Use OpenRouter (Claude 3.5 Sonnet) to extract the business model and summary.
- **Frontend (Streamlit):** Add a detailed expandable card/view when clicking a coin to show its AI-generated business model description and revenue mechanics.
- STATUS: 🔒 LOCKED

### 📌 Feature 3: Social & Developer Metrics Tracker
- **Backend:** Connect to GitHub API and X/LunarCrush API to monitor developer activities and social media volume.
- **Frontend (Streamlit):** Integrate charts showing the correlation between social media volume spikes, GitHub commits, and coin price trends.
- STATUS: 🔒 LOCKED

### 📌 Feature 4: Financial News Ingestion Pipeline
- **Backend:** Build an aggregator for Google News RSS and CryptoPanic free API. Use OpenRouter (Claude 3.5 Haiku or DeepSeek-V3) to classify news into specific Narratives and Types (Rumour vs. Actual Happen).
- **Frontend (Streamlit):** Create a dedicated "Live Crypto Intelligence Feed" section displaying categorized incoming news cards color-coded by type (e.g., Yellow for Rumour, Green for Actual Happen).
- STATUS: 🔒 LOCKED

### 📌 Feature 5: Automated "Why Pump" Engine
- **Backend:** Set a backend trigger to flag when a local cached coin price spikes >15%. Instruct OpenRouter to cross-reference active breaking news with the pre-stored business model to generate a report.
- **Frontend (Streamlit):** Add an "Intelligence Reports" section that populates automated markdown cards explaining exactly *why* a particular asset is surging.
- STATUS: 🔒 LOCKED

### 📌 Feature 6: Narrative Beta Correlation Engine
- **Backend:** Implement an algorithm to structure large-cap market leaders (Main Native Coins) vs. small-cap alternatives inside the same dynamic CMC narrative category.
- **Frontend (Streamlit):** Add an alert banner and predictive matrix table highlighting potential micro-cap "catch-up" trades based on institutional flows.
- STATUS: 🔒 LOCKED
