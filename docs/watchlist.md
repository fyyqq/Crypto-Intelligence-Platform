# Watchlist

**Route:** `/watchlist` · **Status:** Live
**Source:** `frontend/frontend/frontend.py::watchlist_page`, `components/watchlist_table.py`, `components/coin_detail.py` (star icon), `state/coin_state.py` (`watchlist_ids`/`toggle_watchlist`/`watchlist_coins`)

A personal watchlist: star any coin from its own detail page, and it shows up here in the same table design as the homepage's coin list, with a live "remove" star of its own.

## Features

<details>
<summary><strong>⭐ Star toggle on the coin detail page</strong></summary>

Next to a coin's name on its own `/coin/[symbol]` page. Gray outline when not watched, filled amber when it is — `CoinState.watchlist_ids.contains(coin["cmc_id"])` drives both the fill color and the icon's `fill` prop. Clicking calls `CoinState.toggle_watchlist(cmc_id)`, which adds or removes that `cmc_id` from `watchlist_ids` (a plain list state var, reassigned wholesale on each toggle rather than mutated in place, matching this class's existing `coin_overrides` convention).
</details>

<details>
<summary><strong>📋 "My Watchlists" table</strong></summary>

Same visual design as the homepage's coin table (`coin_table.py`) — coin icon/name/ticker, narrative + chain badges, price, market cap, 24h volume, 1H/24H/7D % change, 24H/7D trend sparklines — reusing that module's own cell-building helpers directly (`_change_cell`, `_chain_badge`, `_narrative_badge`, `_trend_cell`) rather than duplicating them. Title reads "My Watchlists" (not "Top N Cryptocurrencies"), and "Total Coins" reflects how many coins are actually starred.

Deliberately **not** wired to the homepage's own browsing state (`categories`/`chains`/`search_query`/`sort_key`/pagination) — a personal watchlist is a small, already-curated list, not something that needs narrative/chain filtering, search, sorting, or pagination the way browsing all ~8,000 coins does. `CoinState.watchlist_coins` is its own computed var: filters `all_coins` (with `coin_overrides` merged in, so a live-synced price shows up here too) down to whichever `cmc_id`s are in `watchlist_ids`, sorted by market cap. Rank shows each coin's real, global market-cap position across every coin on the platform (the same number that coin has on the homepage table) rather than a 1..N renumbering within just the watched subset.

An empty state ("Your watchlist is empty — click the star icon on any coin's own page to add it here") shows in place of the table when nothing is starred yet — a plain centered message, 50vh tall.
</details>

<details>
<summary><strong>⭐ Remove star, new leftmost column</strong></summary>

A new column sits before Rank — blank header, filled amber star in every row (every row here is already-watched, so it's never the outline state). Clicking it calls the same `CoinState.toggle_watchlist(cmc_id)` handler as the coin-detail page, which — since every row here is a match — always removes that coin. The click stops propagation so it doesn't also fire the row's own click-to-navigate handler.
</details>

<details>
<summary><strong>🔗 Existing entry points now do real work</strong></summary>

The header profile-menu's "★ Watchlist" row and the coin-detail star icon were both already in place as UI shells before this feature — no changes needed there beyond wiring the star's click handler (see above); the profile-menu link already pointed at this route.
</details>

## Persistence, honestly

`watchlist_ids` is a plain in-memory Reflex state var, not a database column — this app has no real user/auth system (see `global-components.md`'s profile-pill notes), so there's no account to scope a per-user watchlist to. It lives on the server, keyed to the browser's session cookie, so it survives normal page navigation and a real full-page reload of the same browser session, but is lost if the Reflex server process restarts. If a real account system is ever added, this is the piece that would move to a database table keyed by user id.


### Per-account storage (2026-10-01)
When logged in, stars are saved in the `user_watchlist` table under that account and reloaded at login, so every account has its own watchlist. Logged out, stars stay in the browser session only. Login replaces any logged-out stars with the account's saved list.


<details><summary>Coin rows and results are real links</summary>

### 🔧 Follow-up: coin rows and results are real `<a href>` links, not click handlers (2026-10-04 session)
Per explicit request (`el-06/07`): anything that moves to another page is now a plain anchor tag, so middle-click, Ctrl/Cmd-click and "open in new tab" work, instead of a Reflex `on_click` (`go_to_coin` / `go_to_coin_from_search`) that ran `window.location.assign`. **Coin table + `/watchlist` table** (`coin_table.py::_name_link`, `coin_href`; `watchlist_table.py`): the icon + name + ticker is an `rx.link(href="/coin/<symbol>")`; a CSS stretched link (`assets/styles.css`: `.coin-row-linked` is `position: relative`, `.row-link::after` covers the whole row) makes the entire row the link; the row's `on_click` is gone. The star cell and the "Also deployed on" chain dropdown carry `.row-interactive` (`z-index: 1`) so they stay separate controls and don't navigate. **Floating watchlist popup rows** (`frontend.py::_watchlist_popup_row`) and **header search results** (`global_search.py::_global_search_result_row`) are now `rx.link` rows. Because a search-result link no longer clears the typed query via a handler, `CoinState.restore_session` (first `on_load` on every page) now clears `global_search_query` on the next page load. Cards that already were links (news cards, Narrative Radar cards, alert rows, "More …" links) are unchanged; remaining handler-based navigations are actions rather than links (post-login/logout redirect, the logged-out avatar's width-dependent redirect-or-dropdown). The existing document click listener (`chain_pills.js`) still turns plain same-origin anchor clicks into full page loads, so behaviour for a normal click is unchanged. **Verified live**: row link `<a href="/coin/btc">`; elementFromPoint on the rank and price cells hits the row link, on the star cell hits the star (not a link); the chain dropdown opens without leaving the page; search results are `<a href="/coin/btc">` etc.; the watchlist popup row is `<a href="/coin/btc">`; zero console errors. (`.to(str)` is needed before `.lower()` on an untyped dict value inside a foreach.)

</details>
