# Tools

**Route:** `/tools` · **Status:** Live (2026-10-05)
**Source:** `app/services/market_tools_service.py`, `frontend/frontend/state/tools_state.py`, `frontend/frontend/components/tools_page.py`, `frontend/frontend/frontend.py::tools_page`

"Market Tools": eight market-indicator widgets, each in its own card section. Two layouts: Fear & Greed and Altcoin/Bitcoin Season side by side, the rainbow chart full width, then the five TradingView embeds in a 2-column grid (1 column on phones/tablets). No horizontal overflow at 375px.

## Features

<details><summary>Fear & Greed Index</summary>

A semicircle gauge (server-built SVG, 5 colour zones), the value and label in the zone's colour, and Yesterday / Last week / Last month values. **Sources** (chosen in the "Data source" popup): Alternative.me (free, no key, default) or CoinMarketCap (`COINMARKETCAP_API_KEY`, 1-2 credits per refresh). Cached 15 minutes in-process.
</details>

<details><summary>Altcoin / Bitcoin Season</summary>

Index 0-100 = share of the top 50 coins (stablecoins, wrapped/staked/bridged tokens excluded) that beat Bitcoin over the window; 75+ = Altcoin Season, 25 or less = Bitcoin Season, otherwise Neutral. Shows a marker bar, "N of 50 beat Bitcoin", and the 5 best performers. **Sources**: CoinMarketCap 90 days (standard method, needs `COINMARKETCAP_API_KEY`, 1 credit per refresh) or CoinGecko 30 days (free, no key; CoinGecko's free tier has no 90-day figure, so it reacts faster). Cached 30 minutes. blockchaincenter.net was not used: its page is large and ad-heavy, and a self-computed index is themeable.
</details>

<details><summary>BTC / ETH Rainbow Chart</summary>

Drawn server-side as SVG from daily price history (Yahoo Finance chart API, free, BTC from 2014, ETH from 2017; cached 6 hours). It fits `log10(price) = a * ln(days since genesis) + b` by least squares, then draws 9 bands at +/-0.8 residual standard deviations around that line (Fire sale ... Maximum bubble territory), extended one year ahead, with the price line and a dot for today. Header shows the current price and which band it is in. BTC/ETH tabs. **Not identical to blockchaincenter's chart** (their exact bands are not public); it is a fit to the data, labelled as a guide.
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
