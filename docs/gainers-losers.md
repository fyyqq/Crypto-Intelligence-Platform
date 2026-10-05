# Gainers & Losers

**Route:** `/gainers-losers/` · **Status:** In progress. Step 1 of 7 done: price history is being recorded. The page itself is not built yet.
**Source:** `app/models/price_snapshot.py`, `app/services/price_snapshot_service.py`, `app/services/market_data_service.py` (hook), `frontend/frontend/news_catchup.py` (hourly runner), migration `f8a4b6c7d1e3`, tests in `tests/`.

Top gainers and top losers for the Top 100 / 200 / 300 / 400 / 500 coins (by `cmc_rank`), over 24h, 7d and 30d ("1 Month"). The % change is computed from the app's own stored price snapshots, `(price_now - price_then) / price_then * 100`, never from CMC's `percent_change_*` fields.

## Features

<details><summary>Price snapshots (step 1)</summary>

`price_snapshot` table: `coin_id` (the CMC id, same as `coins.cmc_id`; no foreign key so history survives changes to `coins`), `symbol`, `price_usd` (18 decimals, taken straight from the CMC response, because `coins.price_usd` keeps only 8 and would round micro-cap prices to zero), `cmc_rank`, `volume_24h`, `synced_at` (naive UTC, one timestamp per sync). Insert-only: rows are never updated.

**Who writes it:** `MarketDataService._record_snapshots`, called from the two scheduled syncs only: `sync_hot_listings` (top 500, hourly) and `sync_listings` (all coins, daily). It reuses the CMC response those syncs already fetched (no extra API call). The view-driven `sync_ids` (every 60s for whatever is on screen) does not write snapshots: it is partial and would flood the table. Coins with a missing, zero or negative price are skipped. If a snapshot insert fails, it is logged and the price sync still counts as a success.

**What runs it:** the FastAPI scheduler that normally runs these syncs is not running in this setup, so `frontend/news_catchup.py` starts a `hot-sync-snapshots` thread (with the other background workers, on the first homepage or `/news` load) that calls the existing `run_hot_listings_sync` every 10 minutes; that job only calls CMC once its own 1-hour interval is due. Cost: about 3 CMC credits per hour (~2,200/month of the free 10,000). Storage: about 500 rows per hour, ~540K rows at the planned 45-day retention.

**No backfill:** before this table there was no price history at all (`coins` keeps only the latest price), so history starts at the first snapshot. No past prices are invented.
</details>

## Still to build

Window config and lookback (step 2), edge cases incl. dust floor and 45-day cleanup (3), per-window cold start (4), shared gainers/losers ranking (5), the output function (6), and the `/gainers-losers/` page (7).
