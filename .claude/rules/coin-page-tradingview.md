---
paths:
  - "frontend/frontend/state/coin_state.py"
  - "frontend/frontend/components/coin_detail.py"
  - "frontend/frontend/live_prices.py"
  - "app/services/market_pairs_service.py"
  - "app/services/tradingview_symbol_service.py"
---

# Coin page / TradingView chart rules

- **Price display**: every coin USD price goes through `coin_state._fmt_usd` (or a helper calling it, e.g. `_price_display_with_fallback`). Never a fresh `f"${v:.2f}"`: a fixed decimal count eventually rounds a real price to `$0.00`. Check any new price site.
- **Chart symbol** (`_resolve_tradingview_symbol` / `_resolve_chart_symbol`): candidates come from the coin's cached CEX pairs. Exchange priority MEXC > KuCoin > HTX > Bybit, else USD-equivalent quote then volume. Base comes from the pair's own plain ticker (e.g. `BEAMX`), else the coin's ticker. Drop any pair whose USD price is outside 0.5x-2x of the coin's price (same-ticker different asset). Never guess a bare unprefixed symbol; no resolvable pair -> "No live chart" placeholder. DEX-only coins use TradingView symbol search (`tradingview_symbol_service`: prefers name match + USD, excludes synthetic/index, requires chain match).
- Don't pass `range` with `interval` (it overrides the interval). Chart timezone is `Asia/Kuala_Lumpur`. The chart iframe must stay a typed `rx.el.iframe`.
- Known gaps: CatCoin-style short on-chain tickers fail the ticker-prefix check; NEAR's primary contract is a bridged Ethereum token so its CEX pairs are missing (fix in `MarketDataService._upsert_contracts`).
- Unlock link tiers: DeFiLlama Unlocks slug -> `tokenomist.ai/<gecko_id>/unlock-events` -> `defillama.com/token/<TICKER>`. Both sites 403 scripted requests, so verify in a real browser.
- Coin-page alerts, watchlist and Similar Coins: peer groups live in `app/services/peer_groups.py` (`coins.peer_group`); alerts require login (`_login_required` guard).
- X feed: scraping backend was removed on purpose; the UI shows "View on X" links only. Social Insights "See More" uses `_x_search_url` / `_X_CHAIN_SLUGS`.
