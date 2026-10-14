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
8. **Live deploy**: the live site (Contabo, separate code + separate database from local dev) only updates on explicit request ("update the live site", "deploy this") — pushing to GitHub (rule 3) never deploys it by itself. See `.claude/rules/live-deploy.md` for the SSH details and deploy sequence.

## Rule files (`.claude/rules/`)

`reflex-frontend.md` · `process-management.md` · `telegram-news.md` · `openrouter-ai.md` · `coin-page-tradingview.md` · `auth-sessions.md` · `testing-and-docs.md` · `live-deploy.md`

## Pages and status (details in `docs/README.md`)

Notifications `/notifications` · Home `/` (coin table, filters, news strip, Narrative Radar) · Coin `/coin/[symbol]` · News `/news`, `/news/<cat>`, reader · Narrative `/narrative[/<slug>]` · Gainers & Losers `/gainers-losers` (under Tools) · Tools `/tools` (landing) + `/tools/market-indicators` + `/tools/market-charts` · Watchlist `/watchlist` · Alerts `/alerts` · `/login`, `/signup` · Chains `/chains` (placeholder).

## Current State (2026-10-05)

- Coin pages have a "Related News" link to `/narrative/<category>`; `/narrative/[narrative_slug]` exists. (The category/coin pill sliders above the coin news were removed on request.)
- `/tools` is live (Fear & Greed, Altcoin Season (computed; the blockchaincenter embed was removed), BTC/ETH rainbow on the standard BTC curve with CoinMetrics 2010+ history, TradingView embeds, API-key popup). Details: `docs/tools.md`.
- Gainers & Losers (`/gainers-losers`, reached from the Tools dropdown / `/tools` card, no navbar link of its own) is live: own % change from `price_snapshot` (hourly hot sync, run from the Reflex process by `news_catchup._hot_sync_loop`), 24h/7d/30d, Top 100-500. History started 2026-10-05, so boards show "collecting" until 20h / 6d / 28d of history exist. Tests: `python -m pytest tests` (needs `requirements-dev.txt`). Details: `docs/gainers-losers.md`.
- Gainers & Losers tiers are non-overlapping rank bands (Top 100, 101–200, …) and a calendar button shows past days' boards, saved daily (UTC) into `movers_daily` since 11 Oct 2026; also a 1h window, a per-board refresh icon (forced CMC top-500 sync, global 5-min cooldown) and a Change-column sort toggle (2026-10-12).
- Header bell + `/notifications` (2026-10-12, **local only, not deployed**): every triggered price alert adds a notification; new kinds plug into `notification_service.KINDS`. Details: `docs/notifications.md`.
- `/tools` split (2026-10-14, **local only, not deployed**): `/tools` is now a landing page with two link cards; Fear & Greed + Altcoin Season + Rainbow moved to `/tools/market-indicators`, the five TradingView charts to `/tools/market-charts`; the header Tools link has a hover dropdown to both plus Gainers & Losers and `/tools/crypto-calendar` (a month-by-month calendar parsed from the @layergg calendar posts; Feb-Oct 2026, no Jan/May post). Backfill: `python -m scripts.backfill_layergg_calendar` (stop the Telegram listener first). Details: `docs/tools.md`.
- Homepage overview cards (2026-10-14, **local only, not deployed**): card 1 Market Status (Fear & Greed gauge, Market Cap, Top 20, Altcoin Season; free CoinGecko/Alternative.me data shared with `/tools`), card 2 top-5 gainers/losers of the Top 100 over 24h (2 pages, same snapshots as `/gainers-losers`), card 4 "Incoming News" with sample (dummy) items; card 3 still empty. Details: `docs/home.md`.
- Telegram alerts (2026-10-14, **local only, not deployed; needs `alembic upgrade head` + `TELEGRAM_BOT_TOKEN` and `TELEGRAM_BOT_POLLING=true` (live only, one poller per token) in the server `.env`**): `/notifications` has a Connect Telegram card; triggered price alerts are also sent by `@repace_alerts_bot` to the connected account, and the bot answers `/alerts` and `/alert ETH`. Details: `docs/notifications.md`.
- Telegram Gainers & Losers (2026-10-14, deployed): commands `/gainers_losers_24h|_7d|_1m[_top100..500]` `/fear_greed_index`, `/site_health` (data/pipeline health check, command only), `/view_all_command`, past days `/gainers_losers_<tf>_<band>_<d_m_yyyy>`; automatic only at 08:00 KL daily: the 24H Top 100 board + the Fear & Greed Index (nothing else is auto-sent). Details: `docs/gainers-losers.md`.
- Local dev auto-login (`DEV_AUTO_LOGIN_EMAIL` in the local `.env`, localhost only): the local site is always logged in as the dummy user; see `.claude/rules/auth-sessions.md`. Never set on a server.
- Login wall + Google sign-in (2026-10-14): every page needs a login (logout lands on /login); Google Identity Services button -> `/api/auth/google` (google-auth ID-token verification, allowed existing accounts only). Deployed and verified 2026-10-14 (button loads without errors locally and on live; origins localhost:3000, localhost, repace.fyqqflow.com); `GOOGLE_CLIENT_ID` is in both `.env` files (never the secret).
- Alerts and the coin information panel follow the live price (alert dialog, 24/7 server checker with DEX/contract fallback, market cap/FDV re-based, Liq/Mkt Cap from DexScreener) instead of the stale stored CMC price (2026-10-14).
- Coin pages: red report icon next to "<Coin> Live Chart" opens a chart picker; a hand-picked TradingView symbol is saved permanently per coin (`chart_symbol_overrides`, migration `d5e8f1a3b7c9`) (2026-10-13).
- Coin-page TradingView charts now fill the available center column on desktop and the full padded content width on tablet/mobile; the iframe remains width-constrained by its responsive parent on every coin route (2026-10-14).
- TradingView charts now have independent 1m/5m/15m/1h/4h/D/W presets on coin pages and all five `/tools` embeds.
- Instant clicks (`assets/instant_ui.js`): table skeleton, stars, watchlist/bell popups and header search react in the browser in ~5-120 ms instead of waiting a server round trip; chart symbol is CEX first, DEX only on the coin's chain; DexScreener contract price as the last live-price fallback; weekly CMC metadata sync (X links, contracts) (2026-10-13).
- Live slowness root cause found 2026-10-13: the news pipeline (every 30 min, ~25 min of CPU per run) ran as a thread inside the web server and starved it of the GIL (5-40s page waits); it now runs as its own `nice 10` process (`app/scheduler/news_job.py`), and the background workers start at server start. Deploy + restart needed on live.
- Gainers & Losers keeps moving without CMC: hourly snapshots fall back to the free exchange price list (`record_hub_snapshots`); the 1h window was removed (2026-10-13).
- Price alerts run on the server 24/7 (`frontend/alert_watcher.py`, every 10s, no tab needed) and every notification goes through `notification_service.register_channel` hooks (ready for Telegram/WhatsApp, none connected). CMC credit guard `app/services/cmc_budget.py` pauses optional CMC calls when credits are needed for the hourly/daily syncs (2026-10-13).
- Private mode + in-memory sessions (2026-10-13): `ALLOWED_LOGIN_EMAILS` turns the site into a login-only site for listed accounts (set on live for the owner); Reflex session state moved from disk pickles (~22 MB rewritten per event) to memory and the coin list is shared across sessions: fresh-session load ~1.3s for home/Gainers, coin page 13.5s -> ~5.6s.
- Speed + real-time prices (2026-10-13): the full coin list is server-only (homepage ~72 MB -> ~0.5 MB, coin page ~221 MB -> ~2.3 MB per 30s); homepage/watchlist prices refresh every 30s from the shared exchange price list `app/services/price_hub.py` (no CMC credits); the coin page header price updates every second from the chart's pair. Details: `docs/home.md`, `docs/single-coin-page.md`.
- `/tools` rainbow charts show a live spot price (free exchange tickers, every 15s) and a hover/tap tooltip with band levels; Fear & Greed / Season fall back to free sources when CMC fails (2026-10-13). CMC credit guards: view-sync 10-min shared throttle, failed-sync backoff, re-used-slug fix (`market_data_service`).
- Coin pages show our own 24h change under Market cap and Volume (vs. the `price_snapshot` row ~24h ago; daily all-coin snapshots via `jobs.run_listings_sync`, run from Reflex). Shows nothing until a ~24h-old snapshot exists. Details: `docs/single-coin-page.md`.
- Backend exceptions are written to `logs/error.log` (gitignored) with a reference id shown in the "An error occurred" toast (2026-10-13, **not deployed yet**; local Reflex not restarted). Details: `docs/global-components.md`.
- Telegram posts are merged into the main `/news` sections on purpose (see `telegram-news.md`).
- Telegram media is bounded (webp, 30-day prune, 4.6GB->133MB) and video posts now embed Telegram's own player in the reader (real inline playback, nothing stored); cards still show just the poster. See `telegram-news.md` / `docs/news.md`.
- The Telegram listener is not auto-started by a process manager (the `/news` catch-up starts it).
- `.claude/rules/` and the slim CLAUDE.md were introduced on 2026-10-05; the full prior text is in `docs/CHANGELOG.md`.
- Live SSH: the hostname now resolves to Cloudflare (no port 22), so use `ssh deploy@207.180.233.86` (2026-10-14).
- **Live site is up**: https://repace.fyqqflow.com on Contabo (separate code clone + separate DB from local dev), deployed 2026-10-06. Deploy on request only — see `live-deploy.md`.

## Open items

- **CMC credits exhausted until 1 Nov 2026** (15,000/month plan, shared by local + live: same key). All CMC syncs fail with 429 until then, so coin prices/Gainers & Losers stop updating. Causes fixed 2026-10-13 (daily sync failing on a re-used slug and retrying every 10 min; per-viewer 60s view-sync). Options: a free price fallback (e.g. CoinGecko) or a separate key for local dev.

- Dynamic-route hard loads return HTTP 404 under `--single-port` (reader, coin page); needs a deployment-level SPA fallback.
- NEAR chart missing: primary contract is a bridged Ethereum token (`MarketDataService._upsert_contracts`).
- News dedup is planned but deferred until the user decides which copy to keep (memory: `project_news_dedup_plan`).
- Feature 2 (`ai-instructions.md`) still says LOCKED / Claude 3.5 Sonnet / side-drawer; the build is inline and on-demand with OpenRouter free models. Decide whether to update the spec.
- Optional: remove the 8 artificial `asyncio.sleep(0.25)` skeleton delays; move `telegram_session.session` out of `~/Documents`; add the `Secure` cookie flag over HTTPS.
- `/chains` is still a placeholder page.
- Notion pages for Tools, Single Coin Page and Narrative were requested but not updated: the Notion tools were unavailable in the session of 2026-10-05 (mirror from `docs/`).
- Untracked scratch images at the repo root (`before-click.png`, `chat-open-light.png`) are not committed.
