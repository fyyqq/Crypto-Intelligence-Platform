# Single Coin Page

**Route:** `/coin/[symbol]` (ticker-based, e.g. `/coin/btc` — ties broken by market cap since tickers aren't unique on CMC) · **Status:** Live, actively evolving
**Source:** `frontend/frontend/components/coin_detail.py`, `state/coin_state.py`, `app/services/business_summary_service.py`, `description_ai_service.py`, `market_pairs_service.py`, `tradingview_symbol_service.py`

This page corresponds to the original "Feature 2: Knowledge Base & AI Business Model Agent" plan and the "Single Page Coin" idea sketched in this project's Notion workspace — but **the real implementation deviates from both in two structural ways**, by deliberate choice partway through building it:
- **No side-drawer/modal** — the AI content lives inline in the page itself, in the same layout position a "dummy sentiment" placeholder originally sketched for the right column.
- **No scheduled background worker** — every AI/data step below runs **on-demand**, triggered the first time a visitor opens that specific coin's page, not proactively for the whole Top 500 on a schedule.

Both are open architecture decisions — see `CLAUDE.md`'s Next Steps for the pending choice between formally adopting this as the real design vs. building the originally-planned pieces.

---

## Features

<details>
<summary><strong>💲 Price header</strong></summary>

Big real-time price, 24h % change, coin icon/name/ticker/rank. Same zero-price fallback as the homepage table (falls back to the coin's own top-volume real market pair when CMC's own price is exactly $0). Decimal display never rounds a real nonzero price down to "$0.00" regardless of how small — see this project's Coin Price Display Rule in `CLAUDE.md`.
</details>

<details>
<summary><strong>📈 Live TradingView chart</strong></summary>

A real, symbol-resolved TradingView widget — not a static image or something this app polls/caches; it's the same live-streaming chart technology tradingview.com's own site uses.

Symbol resolution, in order:
1. This coin's own real CEX market pairs, ranked by 24h volume with a real USD/USDT/other-stablecoin pair always outranking a foreign-fiat one regardless of volume (a high-volume Korean-Won pair on Upbit was confirmed live to otherwise beat a real but lower-volume USDT pair, making the chart's price look wrong next to this page's own USD header even though the listing itself was real — not a wrong-coin bug, just the wrong currency), mapped to TradingView's own exchange prefix — never a bare unprefixed guess, which was confirmed live to sometimes resolve to a completely different, malformed symbol.
2. If no real CEX pair exists, falls back to TradingView's own symbol-search API for a DEX pool match, filtered to real spot results and preferring one whose description actually names this coin, whose exchange label confirms the same on-chain platform when that's known, and whose own currency is USD when a choice exists — this closes a real bug where several tickers/names are reused by multiple unrelated real coins on different chains.
3. If neither resolves to a real listing, shows an honest "No live chart available for this coin" placeholder rather than TradingView's own broken-looking error card or a guess.

Default interval is 1 hour, clock shown in Kuala Lumpur time. Built as a real, stable React prop rather than a raw HTML string, so background data syncs elsewhere on the page don't tear down and rebuild the chart — that was previously resetting the viewer's manually-chosen interval roughly every 60 seconds.

When a coin's real cached CEX pairs include all three of MEXC, KuCoin, and Binance, the chart picks MEXC first, then KuCoin, then Binance, overriding the usual USD-equivalent-quote/volume ranking for that one coin only — any other real exchange in the list just sorts after those three rather than being excluded. Falls through to the normal ranking whenever all three aren't present.
</details>

<details>
<summary><strong>🔒 Locked Supply section</strong></summary>

No free vesting/unlock-schedule API exists at any tier (CoinMarketCap has none; CryptoRank Pro is $4,750/yr; DeFiLlama's real emissions endpoint is Pro-only at $300/mo; CoinGecko's closest endpoint is also paid) — checked and confirmed paywalled before building anything. Shows `max_supply - circulating_supply` instead, as an honest supply-math-based fallback: locked amount, locked USD value at the current price, % of max supply, and a supply-range meter (green fill for the circulating portion). Rendered right after the Tags section, only when a coin actually has a max supply greater than its circulating supply — entirely absent otherwise (e.g. ETH, which has no max supply at all). Broadly applicable, not a rare edge case: roughly 1,700 of the top 2,000 ranked coins have a real supply gap.

Below the meter, a "View live unlock data" link — this app can't pull real unlock dates/schedules for free (same paywall as above), so this only ever links out to a real public, no-auth website for a human to read, never fabricated data. Resolving *which* page to link to for a given coin is itself real work, tried in three tiers:
1. **Real per-project DeFiLlama match** — DeFiLlama's own `/protocol/unlocks/<slug>` page for a project with a real, tracked vesting schedule. The `<slug>` comes from matching this coin's own on-chain contract address, then its CoinGecko id, then (last resort) its CMC id against DeFiLlama's public data — never a guessed slug from the coin's name (confirmed live that a naive guess breaks even for unambiguous names, e.g. "Arbitrum" → "arbitrum" 404s; the real page is "arbitrum-foundation").
2. **No DeFiLlama project match** (most coins — its Unlocks feature only tracks projects with a real vesting schedule to show) — links to **tokenomist.ai**'s own per-coin page (`tokenomist.ai/<gecko_id>/unlock-events`), a separate dedicated unlock-tracking site that may cover a project DeFiLlama's own Unlocks feature doesn't. Keyed by this coin's CoinGecko id, confirmed live that's tokenomist's real slug convention too (its ticker-based URL 404s: `/fet/unlock-events` fails, `/fetch-ai/unlock-events` is real) — reuses the exact same CoinGecko-id lookup tier 1 already depends on, no new external data source.
3. **No CoinGecko id known either** (coin outside that lookup's top-500 coverage) — falls back to DeFiLlama's own per-ticker **Token** page (`defillama.com/token/<TICKER>`) as the final safety net. Confirmed live this per-ticker page is real for any listed coin even with no unlock schedule at all — e.g. FET/Artificial Superintelligence Alliance has no Unlocks page under any slug, but `defillama.com/token/FET` is real.

Neither defillama.com nor tokenomist.ai's page-existence can be live-checked from this app's backend — both sit behind Cloudflare bot-protection that returns 403 to *any* plain scripted request, valid URL or not (confirmed via `curl` for both sites) — so each tier above is resolved from known-real data (contract/gecko-id/cmc-id matches, or a confirmed-real page pattern), never a live 404 probe.
</details>

<details>
<summary><strong>🤖 AI business summary</strong></summary>

On first visit, an on-demand call to OpenRouter (a free nemotron model — not Claude 3.5 Sonnet as originally planned, since that model is retired from OpenRouter and this project's OpenRouter account is free-tier) generates a category badge (e.g. "Tokenized Securities Lending Protocol") plus 2–3 titled paragraphs. Falls back to the coin's real CMC narrative tag (e.g. "Layer 1") when no AI category has been generated yet, so every coin's page shows some badge. Re-generated periodically (60-day cache), not one-time, since a project's real business model can drift.
</details>

<details>
<summary><strong>📝 About section — real description upgrade</strong></summary>

Two independent, one-time upgrade steps replacing CMC's generic auto-generated boilerplate description: first, CoinGecko's own curated contract-address lookup if one exists for this coin; if still boilerplate after that (common for memecoins/new listings with no real whitepaper anywhere), a grounded AI paragraph generated from the coin's own website text and/or cached social posts, explicitly forbidden from inventing business-model/tokenomics/team details not present in the source text. Left untouched rather than fabricated when there's genuinely nothing to ground it in.
</details>

<details>
<summary><strong>💱 Real market pairs — Markets tab</strong></summary>

Real CEX and DEX trading pairs sourced from CoinGecko (CMC's own market-pairs endpoint 403s on this project's free API tier), filtered to each venue's real top-15 ranking and never padded if fewer real listings exist. USDC-quoted pairs are dropped in favor of the same exchange's non-USDC pair where one exists. Paginated 10 rows per page per tab, independently for CEX vs. DEX. The tab auto-switches to whichever side actually has real listings when the other is empty. Refreshed hourly, since exchange volume goes stale much faster than the AI summary or description above.
</details>

<details>
<summary><strong>🐦 X / social posts section</strong></summary>

UI-only right now — a horizontal slider of "View on X" cards linking to the coin's real X profile. Real post scraping was tried via two different third-party actors and later removed entirely per explicit request over cost and reliability concerns; the fallback-link UI that already existed for the "not scraped yet" case is now the permanent, only state.
</details>

<details>
<summary><strong>⭐ Watchlist star</strong></summary>

Next to the coin's name — gray outline when this coin isn't watched, filled amber when it is, toggled by `CoinState.toggle_watchlist`. Adding/removing here is what populates or empties the `/watchlist` page's own table. See [Watchlist](./watchlist.md) for the full feature.
</details>

---

## Known, accepted gaps

- No scheduled batch worker for the Top 500 and no side-drawer modal — both deliberate deviations from the original plan, not yet formally re-approved in the spec.
- A few real coins' TradingView charts correctly show "No live chart available" rather than a wrong chart, even though a real chart theoretically exists somewhere with a ticker/chain mismatch this app's matching logic can't safely resolve — treated as an acceptable trade-off, not a bug to chase further right now.
