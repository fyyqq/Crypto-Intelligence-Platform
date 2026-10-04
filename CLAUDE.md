# Repace: Crypto Intelligence Platform

Reflex (Python) frontend in `frontend/`, FastAPI backend + scheduler in `app/`, Postgres (+ a Reflex SQLite mirror of `coins`). Run with `reflex run --env prod --single-port` (port 3000). Details are in `.claude/rules/` (loaded by path) and `docs/` (per-page state). The old 350 KB changelog is archived at `docs/CHANGELOG.md` (do not load it).

## Core rules

1. **Coin prices**: format every USD price through `frontend/frontend/state/coin_state.py::_fmt_usd` (or a helper that calls it). Never an ad hoc fixed-decimal string (it rounds real prices to `$0.00`).
2. **Theme**: text and surfaces must follow light/dark mode. Use `var(--gray-12)` / `var(--gray-11)` / `var(--gray-a2)`, never hardcoded white/black on themed surfaces (especially AI-generated text). Check light mode after UI changes.
3. **Commit and push**: after each verified change, `git add <specific files>` (run `git diff` first, never `git add -A`), commit with a 1-2 sentence "why", and `git push origin main` with local git. Unrelated uncommitted edits in the tree may be another session's work: leave them alone. (Pushing has failed with 403 when git auth uses the wrong account; the owner account is `fyyqq`.)
4. **Docs**: when a page's behaviour changes, update the matching `docs/<page>.md` (shared header/footer/search/floating widgets: `docs/global-components.md`) in the same change. Notion mirroring only on request. See `.claude/rules/testing-and-docs.md`.
5. **Handoff**: after significant work, add or refresh one line under Current State below (keep it under ~20 lines; move older items into `docs/`), plus any open item under Open items.
6. **Verify, don't assume**: test UI headless (Playwright MCP or Claude-in-Chrome), report console errors honestly, and wait for a real HTTP 200 after restarts.
7. **Process hygiene**: exactly one Reflex process pair and one Telegram listener. Stop old PIDs individually before starting. See `.claude/rules/process-management.md`.

## Rule files (`.claude/rules/`)

`reflex-frontend.md` · `process-management.md` · `telegram-news.md` · `openrouter-ai.md` · `coin-page-tradingview.md` · `auth-sessions.md` · `testing-and-docs.md`

## Pages and status (details in `docs/README.md`)

Home `/` (coin table, filters, news strip, Narrative Radar) · Coin `/coin/[symbol]` · News `/news`, `/news/<cat>`, reader · Narrative `/narrative[/<slug>]` · Tools `/tools` · Watchlist `/watchlist` · Alerts `/alerts` · `/login`, `/signup` · Chains `/chains` (placeholder).

## Current State (2026-10-05)

- Coin pages have a "Related News" link to `/narrative/<category>`; `/narrative/[narrative_slug]` exists. (The category/coin pill sliders above the coin news were removed on request.)
- `/tools` is live (Fear & Greed, Altcoin Season (computed; the blockchaincenter embed was removed), BTC/ETH rainbow on the standard BTC curve with CoinMetrics 2010+ history, TradingView embeds, API-key popup). Details: `docs/tools.md`.
- Telegram posts are merged into the main `/news` sections on purpose (see `telegram-news.md`).
- The Telegram listener is not auto-started by a process manager (the `/news` catch-up starts it).
- Local commits may be unpushed until git auth is switched to `fyyqq`.
- Notion is stale versus `docs/` (mirroring is optional now).
- `.claude/rules/` and the slim CLAUDE.md were introduced on 2026-10-05; the full prior text is in `docs/CHANGELOG.md`.

## Open items

- Dynamic-route hard loads return HTTP 404 under `--single-port` (reader, coin page); needs a deployment-level SPA fallback.
- NEAR chart missing: primary contract is a bridged Ethereum token (`MarketDataService._upsert_contracts`).
- News dedup is planned but deferred until the user decides which copy to keep (memory: `project_news_dedup_plan`).
- Feature 2 (`ai-instructions.md`) still says LOCKED / Claude 3.5 Sonnet / side-drawer; the build is inline and on-demand with OpenRouter free models. Decide whether to update the spec.
- Optional: remove the 8 artificial `asyncio.sleep(0.25)` skeleton delays; move `telegram_session.session` out of `~/Documents`; add the `Secure` cookie flag over HTTPS.
- `/chains` is still a placeholder page.
- Notion pages for Tools, Single Coin Page and Narrative were requested but not updated: the Notion tools were unavailable in the session of 2026-10-05 (mirror from `docs/`).
- Untracked scratch images at the repo root (`before-click.png`, `chat-open-light.png`) are not committed.
