# Tools

**Routes:** `/tools` (landing) · `/tools/market-indicators` · `/tools/market-charts` · **Status:** Live (2026-10-05); split into sub-pages 2026-10-14 (**local only, not deployed**).
**Source:** `app/services/market_tools_service.py`, `frontend/frontend/state/tools_state.py`, `frontend/frontend/components/tools_page.py` (`TOOL_PAGES`, `tools_home_content`, `market_indicators_content`, `market_charts_content`), `frontend/frontend/frontend.py` (`tools_page`, `market_indicators_page`, `market_charts_page`, `_dropdown_nav_item`), card styles `.tool-card` in `assets/styles.css`.

**Structure (2026-10-14).** `/tools` used to hold everything on one long page; it is now a clean landing page: the title "Market Tools" and a two-column grid (stacked on phones) with one large link card per tool: Market Indicators, Market Charts and **Gainers & Losers** (3rd card, links to `/gainers-losers`, which also keeps its own header link; added 2026-10-14). Each card (a real `<a>`) has an accent-tinted icon tile, the title, a one-sentence description, chips naming what is inside, and an "Open ->" footer; on hover it lifts, gets an accent border and the arrows nudge. The list is the single `TOOL_PAGES` list, which also feeds the header's **Tools dropdown** (hover, like News): Market Indicators, Market Charts, Gainers & Losers. "Tools" stays highlighted on every sub-page, and each sub-page has a "<- Market Tools" back link above its title.
- **`/tools/market-indicators`** (Market Indicators): Fear & Greed and Altcoin / Bitcoin Season side by side (one column below 1280px), then the full-width BTC / ETH Rainbow Chart, with the data-source popup. Loads `ToolsState.refresh_fng`, `refresh_season`, `refresh_rainbow` (which starts the rainbow live loop) and `rainbow_hover.js`; the landing page and the charts page load none of that.
- **`/tools/market-charts`** (Market Charts): the five TradingView embeds in a 2-column grid (DXY, total market cap, BTC dominance, ETH/BTC, TOTAL2), each with its own 1m-W timeframe buttons (`tradingview_timeframes.js` is global). No ToolsState events.
The homepage Market Status card's title now links to `/tools/market-indicators`. Verified in light and dark at 1440 / 1024 / 834 / 375: no overflow, no horizontal scroll, zero console errors; the old content is gone from `/tools` (no iframes, gauge or rainbow there).

The sections below describe each widget (they now live on the sub-pages above).

## Features

<details><summary>Fear & Greed Index</summary>

A semicircle gauge (server-built SVG, 5 colour zones), the value and label in the zone's colour, and Yesterday / Last week / Last month values. **Sources** (chosen in the "Data source" popup): Alternative.me (free, no key, default) or CoinMarketCap (`COINMARKETCAP_API_KEY`, 1-2 credits per refresh). Cached 15 minutes in-process.
</details>

<details><summary>Altcoin / Bitcoin Season</summary>

Index 0-100 = share of the top 50 coins (stablecoins, wrapped/staked/bridged tokens excluded) that beat Bitcoin over the window; 75+ = Altcoin Season, 25 or less = Bitcoin Season, otherwise Neutral. Shows a marker bar, "N of 50 beat Bitcoin", and the 5 best performers. **Sources**: CoinMarketCap 90 days (standard method, needs `COINMARKETCAP_API_KEY`, 1 credit per refresh) or CoinGecko 30 days (free, no key; CoinGecko's free tier has no 90-day figure, so it reacts faster). Cached 30 minutes. blockchaincenter.net was not used: it offers no public chart widget or data API (only a share-card image of the gauge), and embedding their whole page was tried and removed (their header/ads came with it; cropping it to just the chart would be fragile). CoinMarketCap, Coinglass and Alternative.me block iframes.
</details>

<details><summary>BTC / ETH Rainbow Chart</summary>

Drawn server-side as SVG from daily USD prices: **CoinMetrics' free community API** (BTC from 18 Jul 2010, ETH from Aug 2015; no key), with Yahoo Finance (BTC from 2014) as fallback; cached 6 hours. **Bitcoin** uses the widely used logarithmic-growth curve as the centre, `log10(price) = 2.66167 * ln(days since 2009-01-09) - 17.9183`, with nine bands spanning +/-0.6 decades around it (this is what Blockchaincenter/Coinglass-style charts use; an earlier version fitted its own regression on 2014+ data with wider bands and so looked different, with BTC reading "Still cheap" instead of "Fire sale"). **Ethereum** has no standard curve, so its centre is a least-squares fit of its own history and its bands span the historical envelope around that fit. The bands are extended about 1.5 years ahead; the header shows the current price and band; BTC/ETH tabs. Labels and colours follow the common rainbow charts (Fire sale ... Maximum bubble territory).
</details>

<details><summary>Rainbow chart: live price and hover tooltip (2026-10-13)</summary>

**Live price.** The history (CoinMetrics daily closes) only goes up to yesterday's close, so the headline price used to be that close (cached 6h). Now `market_tools_service._live_spot` reads the spot USD price from free public exchange tickers, no key: Coinbase, then Kraken, then Binance (USDT); cached 10s. `ToolsState.rainbow_live_loop` re-reads it every 15s while the page is open and moves the price (through `_fmt_usd`), the band badge, a "Live · <time> UTC · <source>" line with a pulsing dot, and the chart's last segment + live dot. The chart itself (`rainbow_svg`, cached 6h) is not re-sent: the live part is a tiny overlay SVG with the same viewBox stacked on top (`rainbow_live()` -> `rainbow_overlay`, `.rainbow-overlay`). If every ticker fails, it falls back to the last daily close ("as of <date> (daily close)").

**Hover / tap tooltip** (free, our own code, no library or service): `assets/rainbow_hover.js` reads the chart model sent once per asset in `data-rainbow` on `.rainbow-chart` (geometry, band model `slope`/`icpt`/`lo`/`step`, and every daily close). On hover (or tap on touch screens) it draws a vertical guide, a dot on the price line, and a card with the date, that day's price, and all nine bands' price levels at that date with the price's band highlighted. Future dates show "Projected bands". Prices in the card mirror `_fmt_usd`; band levels are compact ($46.1K) like the axis. Touch: the card stays until a tap outside the chart; vertical scrolling still works (`touch-action: pan-y`). Theme tokens only (`.rainbow-tip` in styles.css).
</details>

<details><summary>CoinMarketCap fallback for Fear & Greed and Season (2026-10-13)</summary>

When the chosen source is CoinMarketCap and it fails (rate limit / monthly credits used up / key rejected / unreachable), the card shows the free source's result instead (Alternative.me for Fear & Greed, CoinGecko 30 days for Season) with an amber note "CoinMarketCap unavailable (<reason>), showing <source> instead." A failed CMC source is not retried for 10 minutes (`_with_cmc_fallback`, `_CMC_FAIL_TTL`).
</details>

<details><summary>TradingView embeds: DXY, total market cap, BTC dominance, ETH/BTC, TOTAL2</summary>

Free `widgetembed` iframes (same mechanism as the coin page chart), daily candles by default, KL timezone, light/dark via `rx.color_mode_cond`. Each chart has independent 1m, 5m, 15m, 1h, 4h, D, and W controls. Symbols: `CAPITALCOM:DXY`, `CRYPTOCAP:TOTAL`, `CRYPTOCAP:BTC.D`, `BINANCE:ETHBTC`, `CRYPTOCAP:TOTAL2`. **`TVC:DXY` (the usual DXY symbol) is blocked in embeds** ("only available on TradingView"), so DXY uses Capital.com's index, which tracks the same value. No key needed.
</details>

<details><summary>Data source popup and API keys</summary>

Fear & Greed and Season each have a "Data source" button that opens a popup listing the sources with a badge: "No key needed", "Key found in .env", or "Key missing". A source with a key shows the exact line to add (`NAME=your_key` in the project-root `.env`). **"Re-check .env"** re-reads the file, so a newly added key works without restarting the app. The popup opens by itself, and the widget shows an "API key needed" card, when the viewer's chosen source has no key. The choice is saved per browser (localStorage `repace_tools_fng_source` / `repace_tools_season_source`); with no choice the first usable source is used. `.env` is trusted over the process environment when the file exists (the app loads it at startup, so the environment would keep reporting a removed key).
</details>

## Verified live

All eight sections render with live data (F&G 65 Greed, Season 64 Neutral with 32/50, BTC $85.3K "Still cheap", ETH tab works, five charts load, DXY 101.56); switching F&G to CoinMarketCap changes the source line; with the CMC key removed from `.env` the popup opened by itself with "Key missing", and after restoring it "Re-check" cleared it with no restart; zero console errors.

## Known gaps

Rainbow-chart bands are our own fit. The Season index is not blockchaincenter's exact figure. The key popup only explains where to put the key; keys are never typed into the page or written by the app.
