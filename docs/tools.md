# Tools

**Route:** `/tools` · **Status:** Live (2026-10-05)
**Source:** `app/services/market_tools_service.py`, `frontend/frontend/state/tools_state.py`, `frontend/frontend/components/tools_page.py`, `frontend/frontend/frontend.py::tools_page`

"Market Tools": nine market-indicator sections, each in its own card section. Layout: Fear & Greed and Altcoin/Bitcoin Season side by side, the Blockchaincenter season embed and the rainbow chart full width, then the five TradingView embeds in a 2-column grid (1 column on phones/tablets). No horizontal overflow at 375px.

## Features

<details><summary>Fear & Greed Index</summary>

A semicircle gauge (server-built SVG, 5 colour zones), the value and label in the zone's colour, and Yesterday / Last week / Last month values. **Sources** (chosen in the "Data source" popup): Alternative.me (free, no key, default) or CoinMarketCap (`COINMARKETCAP_API_KEY`, 1-2 credits per refresh). Cached 15 minutes in-process.
</details>

<details><summary>Altcoin / Bitcoin Season</summary>

Index 0-100 = share of the top 50 coins (stablecoins, wrapped/staked/bridged tokens excluded) that beat Bitcoin over the window; 75+ = Altcoin Season, 25 or less = Bitcoin Season, otherwise Neutral. Shows a marker bar, "N of 50 beat Bitcoin", and the 5 best performers. **Sources**: CoinMarketCap 90 days (standard method, needs `COINMARKETCAP_API_KEY`, 1 credit per refresh) or CoinGecko 30 days (free, no key; CoinGecko's free tier has no 90-day figure, so it reacts faster). Cached 30 minutes. blockchaincenter.net was not used: its page is large and ad-heavy, and a self-computed index is themeable.
</details>

<details><summary>BTC / ETH Rainbow Chart</summary>

Drawn server-side as SVG from daily USD prices: **CoinMetrics' free community API** (BTC from 18 Jul 2010, ETH from Aug 2015; no key), with Yahoo Finance (BTC from 2014) as fallback; cached 6 hours. **Bitcoin** uses the widely used logarithmic-growth curve as the centre, `log10(price) = 2.66167 * ln(days since 2009-01-09) - 17.9183`, with nine bands spanning +/-0.6 decades around it (this is what Blockchaincenter/Coinglass-style charts use; an earlier version fitted its own regression on 2014+ data with wider bands and so looked different, with BTC reading "Still cheap" instead of "Fire sale"). **Ethereum** has no standard curve, so its centre is a least-squares fit of its own history and its bands span the historical envelope around that fit. The bands are extended about 1.5 years ahead; the header shows the current price and band; BTC/ETH tabs. Labels and colours follow the common rainbow charts (Fire sale ... Maximum bubble territory).
</details>

<details><summary>Altcoin / Bitcoin Season: live chart (Blockchaincenter embed)</summary>

A second section below the computed one (which stays): an iframe of **blockchaincenter.net/altcoin-season-index/**, their own index with the Month and Year views, stats table and flip calendar, shown in a 560-720px scrolling card (the frame is 2000px tall so their fixed ad banner sits at the very bottom instead of over the gauge), plus an "Open blockchaincenter.net" link. It is their whole page (header and ad banner included) rather than an official widget, so it can change or add frame blocking at any time. CoinMarketCap, Coinglass and Alternative.me all send `X-Frame-Options: SAMEORIGIN` and cannot be embedded. Their figure (57 on 2026-10-04) differs from our computed index (64) because the methods differ.
</details>

<details><summary>TradingView embeds: DXY, total market cap, BTC dominance, ETH/BTC, TOTAL2</summary>

Free `widgetembed` iframes (same mechanism as the coin page chart), daily candles, KL timezone, light/dark via `rx.color_mode_cond`. Symbols: `CAPITALCOM:DXY`, `CRYPTOCAP:TOTAL`, `CRYPTOCAP:BTC.D`, `BINANCE:ETHBTC`, `CRYPTOCAP:TOTAL2`. **`TVC:DXY` (the usual DXY symbol) is blocked in embeds** ("only available on TradingView"), so DXY uses Capital.com's index, which tracks the same value. No key needed.
</details>

<details><summary>Data source popup and API keys</summary>

Fear & Greed and Season each have a "Data source" button that opens a popup listing the sources with a badge: "No key needed", "Key found in .env", or "Key missing". A source with a key shows the exact line to add (`NAME=your_key` in the project-root `.env`). **"Re-check .env"** re-reads the file, so a newly added key works without restarting the app. The popup opens by itself, and the widget shows an "API key needed" card, when the viewer's chosen source has no key. The choice is saved per browser (localStorage `repace_tools_fng_source` / `repace_tools_season_source`); with no choice the first usable source is used. `.env` is trusted over the process environment when the file exists (the app loads it at startup, so the environment would keep reporting a removed key).
</details>

## Verified live

All eight sections render with live data (F&G 65 Greed, Season 64 Neutral with 32/50, BTC $85.3K "Still cheap", ETH tab works, five charts load, DXY 101.56); switching F&G to CoinMarketCap changes the source line; with the CMC key removed from `.env` the popup opened by itself with "Key missing", and after restoring it "Re-check" cleared it with no restart; zero console errors.

## Known gaps

Rainbow-chart bands are our own fit. The Season index is not blockchaincenter's exact figure. The key popup only explains where to put the key; keys are never typed into the page or written by the app.
