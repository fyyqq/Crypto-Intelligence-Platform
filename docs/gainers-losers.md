# Gainers & Losers

**Route:** `/gainers-losers` · **Status:** Live (built 2026-10-05). Boards fill in as price history accumulates: 24h from about 20 hours after the first snapshot, 7d from about 6 days, 1 Month from about 28 days.
**Source:** `app/models/price_snapshot.py`, `app/services/price_snapshot_service.py`, `app/services/market_data_service.py` (hook), `frontend/frontend/news_catchup.py` (hourly runner), `frontend/frontend/state/gainers_losers_state.py`, `frontend/frontend/components/gainers_losers_page.py`, `app/models/movers_daily.py`, migrations `f8a4b6c7d1e3` and `b3c6d9e1f5a7` (movers_daily), tests in `tests/` (`python -m pytest tests`, needs `requirements-dev.txt`).

Top gainers and top losers per rank band by current `cmc_rank`: Top 100 (ranks 1-100), 101-200, 201-300, 301-400, 401-500. The bands do not overlap (changed 2026-10-12; they used to be cumulative, so "Top 200" repeated the Top 100 coins), over 24h, 7d and 1 Month (a fixed 30 days). The % change is the app's own: `(price_now - price_then) / price_then * 100`, from stored price snapshots, never CMC's `percent_change_*` fields. Linked from the header nav ("Gainers & Losers", and in the profile dropdown below 1280px).

## Features

<details><summary>Price snapshots</summary>

`price_snapshot` table: `coin_id` (the CMC id, same as `coins.cmc_id`; no foreign key so history survives changes to `coins`), `symbol`, `price_usd` (18 decimals, taken straight from the CMC response, because `coins.price_usd` keeps only 8 and would round micro-cap prices to zero), `cmc_rank`, `volume_24h`, `market_cap` (added later the same day; older rows NULL; used by the coin page's 24h market cap change), `synced_at` (naive UTC, one timestamp per sync). Insert-only.

**Who writes it:** `MarketDataService._record_snapshots`, from the two scheduled syncs only: `sync_hot_listings` (top 500, hourly) and `sync_listings` (all coins, daily). It reuses the CMC response those syncs already fetched (no extra API call). The view-driven `sync_ids` (every 60s for whatever is on screen) does not write snapshots. Coins with a missing, zero or negative price are skipped. A snapshot failure is logged and never fails the price sync.

**What runs it:** the FastAPI scheduler is not running in this setup, so `frontend/news_catchup.py` starts a `hot-sync-snapshots` thread (with the other background workers, on the first homepage, `/news` or `/gainers-losers` load) that calls the existing `run_hot_listings_sync` every 10 minutes (the job only calls CMC once its own 1-hour interval is due, ~3 CMC credits/hour) and `run_listings_sync` (every coin, once a day, ~41 credits), so every coin also gets a daily snapshot. About 500 rows per hour, ~540K rows at 45-day retention.

**Overflow guard (fixed 2026-10-05):** the daily full listings sync had been failing since 24 Sep with a numeric overflow (CMC reported a percent change beyond the `coins.percent_change_*` column range for some illiquid token), rolling back every coin. Values that can't fit their column are now stored as NULL (`market_data_service._fit`, and the same guard in `record_snapshots`), so one absurd value no longer blocks the sync; the first successful full sync since then wrote 8,124 snapshots.

**No backfill:** there was no price history before this table (`coins` keeps only the latest price), so history starts at the first snapshot (2026-10-05 04:48 UTC). No past prices are invented.
</details>

<details><summary>Windows and lookback</summary>

One `WINDOWS` config in `price_snapshot_service.py`: `24h` (lookback 24h, accepts snapshots 20-28h old), `7d` (7d, 6-8d), `30d` (label "1 Month", 30d, 28-32d). Adding a window = adding one entry; the page's window buttons are built from the same config. For each coin in the latest sync, `compute_changes` picks the snapshot closest to (latest sync - lookback) inside the tolerance; a missed sync falls back to the next closest inside the tolerance.
</details>

<details><summary>Edge cases</summary>

- **New coins / no history:** no snapshot inside the tolerance means the coin is skipped for that window (it can still appear in a shorter window).
- **Zero or missing price:** never divided by; the coin is skipped.
- **Dust:** coins whose current 24h volume is under `MIN_VOLUME_USD` (50,000) are left out of every board, both directions.
- **Retention:** `cleanup_snapshots` deletes snapshots older than `RETENTION_DAYS` (45), after every scheduled sync. `validate_retention` runs when the module is imported and raises if retention is not longer than the longest window's lookback plus tolerance (32 days); cleanup also refuses to run with an unsafe value.
</details>

<details><summary>Cold start (per window)</summary>

`window_status` says a window is "ready" once a snapshot exists that is 20h-28h (24h), 6-8d (7d) or 28-32d (30d) older than the latest sync, i.e. the baseline `compute_changes` really compares against; otherwise "collecting" with days and hours remaining. A recording gap (e.g. CMC credits ran out 12 Oct 12:50 UTC and nothing was stored until the exchange-price fallback began 13 Oct 13:24 UTC) therefore restarts the clock from the first snapshot after the gap instead of showing a "ready" but empty board (fixed 2026-10-14). Each window is judged on its own. The page shows an hourglass card ("Collecting data for the 7d board ... ready in about N day(s)") instead of an empty or invented table.
</details>

<details><summary>Ranking and output</summary>

`compute_changes` is the one shared calculation; `rank_movers(changes, bucket, direction, limit)` cuts it to the band `bucket_floor(bucket) < rank <= bucket`, then: `gainers` keeps change > 0 sorted descending, `losers` keeps change < 0 sorted ascending (most negative first). 0% is in neither; lists are never padded. `get_movers(db, bucket, window, direction, limit=30)` returns status, time remaining and the coins (rank, name, symbol, price_now, price_then, pct_change, volume_24h, then_at). Unknown windows, buckets or directions raise a clear `SnapshotConfigError`.
</details>

<details><summary>Daily history (calendar)</summary>

Added 2026-10-12. `movers_daily` stores each UTC day's board: per day and window, every qualifying coin up to rank 500 (rank, name, symbol, price now/then, % change, 24h volume, then_at/now_at), unique on (day, window, coin_id). `record_daily_movers` runs in the `hot-sync-snapshots` loop after each sync check (every 10 min). It is a no-op unless a newer sync landed than the day's saved rows. Otherwise it replaces that day's rows for every ready window, so once a UTC day ends its rows are that day's closing board (last hourly sync, ~23:xx UTC = ~07:xx MYT next day). A window that is still collecting is not saved for that day. Kept indefinitely (~1.5K rows/day). History starts 11 Oct 2026 (UTC); nothing earlier is reconstructed.

Page: a calendar button right after the window buttons ("Live" or the picked day, e.g. "11 Oct 2026") opens a popover with a native date input bounded to the first/last saved day (`saved_days`), a "Saved daily (UTC) since ..." note, and "Back to live". Picking a day loads that day's rows (`load_daily_movers`, `GainersLosersState.load_day`). The same window and band buttons re-cut them through `rank_movers`. Each board then shows a calendar badge and "Saved board, as of <time>". A window with nothing saved that day shows a "No saved <window> board for <day>" card with "Back to live".
</details>

<details><summary>Refresh button and Change sort</summary>

Added 2026-10-12. Each board header has a refresh icon on the right (lucide `rotate-cw`, `var(--gray-12)` so it follows light/dark). Clicking it runs `GainersLosersState.refresh`: `app/scheduler/jobs.run_manual_hot_sync` does the same top-500 CMC pull as the hourly sync (~3 credits, upserts coin quotes, records a price snapshot, then copies the Reflex SQLite mirror in a background thread). It is gated by a **global 5-minute cooldown** (`MANUAL_REFRESH_COOLDOWN_MINUTES`, via the `LISTINGS_HOT` SyncLog), so clicks from any number of viewers cost at most ~3 credits per 5 minutes. Inside the cooldown the click only recomputes from the stored data. After a real sync, today's board is re-saved (`record_daily_movers`) and every window is recomputed. The tables stay visible while it runs, and the icon spins (`.gl-refresh-spinning` in `assets/styles.css`, at least one full 360° turn). A refresh always returns to the live board. The tooltip shows the last sync time. Without a click, data still updates hourly; the page does not auto-poll.

The Change header has a sort icon (`arrow-down-wide-narrow` = largest % first, `arrow-up-narrow-wide` = smallest first). Clicking flips the order of that board's 30 coins only; it never swaps in other coins. `#` keeps each coin's biggest-move position. Defaults: Gainers descending (largest increase first), Losers ascending (largest drop first).
</details>

<details><summary>Page</summary>

Window buttons (24h / 7d / 1 Month; the 1h window was removed on request 2026-10-13) and band buttons (Top 100, 101–200, 201–300, 301–400, 401–500; the board badge reads e.g. "24h · Rank 101–200"). Two cards side by side from 1280px (stacked below): Top Gainers (green) and Top Losers (red), up to 30 rows each: position, coin (icon, name, symbol, current rank; links to the coin page), price now with "was <price then>" and the snapshot time used, % change, 24h volume (hidden on phones). Prices go through `_fmt_usd`. On load the state computes all three windows once (`GainersLosersState.load`); switching window or bucket only re-cuts those lists.
</details>

<details><summary>Exchange-price snapshots when CMC can't record the hour (2026-10-13)</summary>

The boards stopped moving on 12 Oct (~13:30 UTC) because their hourly history came only from the CMC top-500 sync, and the CMC key ran out of monthly credits. Now `price_snapshot_service.record_hub_snapshots` runs in the same `hot-sync-snapshots` loop (every 10 min): when no snapshot of any source is less than ~55 min old, it records the top 500 from the free exchange price list (`price_hub`), keeping only prices plausible against the stored price (coins no exchange lists, mostly stablecoins, sit out that hour rather than get a stale price), with the stored rank and 24h volume and the market cap scaled by the price move. When CMC works again its hourly sync records first and this is a no-op. First run locally: 412 coins; the 24h board compared against 12 Oct 13:36, as expected. The saved daily boards (calendar) ignore any old `1h` rows.
</details>

<details><summary>Telegram: commands and automatic digest (2026-10-14, live)</summary>

Source: `app/services/telegram_digest_service.py`, tests `tests/test_telegram_digest.py`. Bot setup and the account link are in `docs/notifications.md`.

**Commands** (connected accounts only): `/gainers_losers_24h`, `/gainers_losers_7d`, `/gainers_losers_1m` (= the 30-day "1 Month" window). Telegram menu commands cannot contain hyphens, so the menu names use underscores; the hand-typed `/gainer-losers-24H` spelling is accepted too. Per-band commands (2026-10-14): `/gainers_losers_<24h|7d|1m>_top<100|200|300|400|500>` (e.g. `/gainers_losers_24h_top200` = ranks 101-200, `_top100` = ranks 1-100); the plain command is the same as `_top100`. A trailing argument also works (`/gainers_losers_24h 200`). 18 menu entries in total (`telegram_digest_service.COMMANDS`, built from `WINDOWS`/`BUCKETS`, so adding a band or window adds its commands). The reply lists the top 10 gainers and top 10 losers from the same `get_movers` data as the page (rank band, % change, price via `_fmt_usd`). A window still collecting replies with a "ready in about N day(s)" notice instead of a board.

**Past days:** `/gainers_losers_13_10_2026` (day_month_year; hyphens also work) replies with that day's saved board from `movers_daily` (the site's calendar, so a UTC day, with "Saved board, as of <time> UTC"). The window and band go before the date: `/gainers_losers_7d_top200_13_10_2026`, `/gainers_losers_1m_top300_13_10_2026`, `/gainers_losers_24h_13_10_2026` (default 24H, Top 100; the date is always last). A day or window with nothing saved says so and lists the first and last saved day; an impossible date (31_02) gets a "not a valid date" hint. These are not in the bot menu (one per date would be endless); `/help` lists the pattern. Parser: `parse_date_command`, builder `build_past_message`.

**Automatic messages (2026-10-14):** only two things are sent automatically, once a day at 08:00 Kuala Lumpur time, to every connected account: the **24H Top 100 board** and the **Fear & Greed Index**. Nothing else is automatic: 7D, 1 Month, other rank bands and past days are on-demand commands only (the 7D-on-Mondays and 1M-on-the-1st digests of the first version were removed on request). The 24H board is sent only when its window is "ready" (otherwise retried each minute until 12h after 08:00); the index only once Alternative.me shows today's UTC value (published at 00:00 UTC = 08:00 KL), so yesterday's number is never sent as "now". Each item is sent once per day (`logs/telegram_digest_sent.json` keeps the last sent day per item, so restarts never repeat or double-send; one failing source never blocks the other). The scheduler is a Reflex lifespan task (`frontend.py::_telegram_digest`, checks every minute) that runs only where `TELEGRAM_DIGEST=true` (live), because local and live share one bot and a second sender would duplicate. There is no per-account opt-out yet.

**`/fear_greed_index`:** replies with the current index and yesterday's (value, label, dot colour by the /tools gauge zones, and the change ▲/▼), from the same free source as `/tools` (Alternative.me, no CMC credits). Every command is a fresh fetch (it skips the tools page's 15-minute cache), so it doubles as a manual refresh. Code: `fetch_fng` / `fng_message` / `handle_fng` in `telegram_digest_service.py`; `market_tools_service._fng_result` now also returns `ts`.

**Not real time:** the boards use the latest stored price snapshot (hourly, ~:42 on live; exchange-price fallback while CMC credits are out) against the snapshot ~24h / 7d / 30d earlier, so repeating a command returns the same board until the next hourly snapshot. A live-price version (shared exchange price list, 30s fresh, vs the same baseline snapshot) is possible but not built.
</details>
