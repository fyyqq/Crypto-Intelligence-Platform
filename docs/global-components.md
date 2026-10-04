# Global Components

**Renders on:** every page (Home, Single Coin Page, and all placeholder pages) · **Status:** Live
**Source:** `frontend/frontend/frontend.py::_header_bar`, `components/global_search.py`, `components/footer.py`

Anything shared across every page lives here, not filed under any one feature page — see this project's `CLAUDE.md` **Feature & Global-Component Documentation Rule**.

---

## Features

<details>
<summary><strong>🧭 Header layout</strong></summary>

A responsive 3-column grid: `1fr auto 1fr` at tablet width and up (true horizontal centering of the nav-links column, regardless of how wide the logo or right-side controls are), `auto minmax(0, 1fr) auto` below that (a plain `1fr auto 1fr` was tried first at phone widths and measured out to around 2px for the middle column — functionally invisible; this fix is what actually gives it real, guaranteed width). The "Repace" wordmark text hides below 480px, leaving just the logo mark, to free space for the rest of the header on a phone.
</details>

<details>
<summary><strong>🔗 Nav links</strong></summary>

News / Narrative / Chains / Tools — each a real page (see [News](./news.md), [Narrative](./narrative.md), [Chains](./chains.md), [Tools](./tools.md)), not an anchor into another page. The link matching the current route highlights in the accent color. Visible at every screen width; below roughly 480px the row becomes a horizontal swipe rather than clipping any link permanently, since all four genuinely don't fit next to the logo and search/profile controls at that width.
</details>

<details>
<summary><strong>🔍 Global search</strong></summary>

Always-visible (70px to 240px depending on screen width), transparent-background search bar, left of the profile pill. A "/" keyboard shortcut focuses it, hidden on touch/phone widths since there's no physical keyboard there. Typing shows a CoinMarketCap-style autocomplete dropdown: up to 5 coin matches by default (icon, name — truncated with an ellipsis rather than wrapping if too long — ticker, real price shown above a smaller 24h-change line), a "Show more" expander, an empty state, and a real "Articles" section heading with an honest "News search isn't available yet" placeholder, since no news-search backend exists. An "x" replaces the "/" badge once there's a query, clearing the field and closing the dropdown in one click. Also closes on a real click anywhere outside it.
</details>

<details>
<summary><strong>👤 Profile pill & dropdown</strong></summary>

Avatar plus "Fyqq / Standard" (the text hides below tablet width, leaving just the avatar). Click opens a dropdown below it; a second click, or a real click outside it, closes it again. Dropdown contents, top to bottom:
- **★ Watchlist** (real navigation to the [Watchlist](./watchlist.md) page)
- **🌙/☀️ Dark Mode / Light Mode** (this used to be its own always-visible header button; moved in here specifically to free the width the nav-links row needed to stay visible at phone widths)

Both rows are styled identically — same full-width padded row, same hover highlight — confirmed live via computed styles after fixing a structural bug where the Watchlist row's styling class had landed on its wrapping link element (inline by default) instead of the inner flex row the Dark Mode item already used, which had made the two rows look visibly different.
</details>

<details>
<summary><strong>🦶 Footer</strong></summary>

Logo/description/social-icon row on the left (Instagram/X/YouTube/LinkedIn/GitHub — real brand SVGs), three placeholder link columns on the right (Product/Resources/Company — no real destinations wired up yet), bottom copyright/legal-links row. Centered/stacked below 1280px, left-aligned two-column layout at 1280px and up.
</details>

<details>
<summary><strong>🪙 Floating logo badge</strong></summary>

A small (56×56px) circular brand mark, fixed to the bottom-right corner of every page. Purely decorative, not clickable. The source artwork supplied for this had no real transparency — it was a checkerboard pattern baked directly into the image's pixels, not an actual alpha channel — so it was re-masked into a clean circular cutout (sampling the coin's own true edge color and fading alpha across a solid band, rather than fading the original checker-contaminated pixels, which left a faint colored halo on the first attempt) before being used here. The artwork was swapped for a second supplied image later the same day, reprocessed the same way. Reflex's own built-in "Built with Reflex" sticky badge, which used to occupy this same corner, is now disabled entirely (a real config setting, not a CSS hack) rather than avoided, so this badge sits flush in the corner rather than stacked above it.
</details>

---

## Notes

This file is the local counterpart to `CLAUDE.md`'s own `### 🌐 Global Components` section and the matching Notion page — kept in sync per the Documentation Sync Rule any time the header, footer, search, or profile menu changes.

<details><summary>Page switches are full reloads</summary>

Navigating between pages (nav links, logo, table row, search result, news cards) is a real browser navigation, done by a capture-phase click listener in `assets/chain_pills.js` plus `window.location.assign` in the two coin-navigation handlers. Filters, sorting, pagination, search and source pills stay reload-free (Reflex state events). Ctrl/Cmd/middle-clicks, new-tab and external links behave normally. Trade-offs: each switch reloads the app data (slower), and dynamic routes log a 404 status on hard load (page still renders).

</details>

<details><summary>Tablet/mobile header and tablet footer</summary>

Below the lg breakpoint (1280px) the header's nav links move into the top of the profile dropdown and the search box is centred in the header (the right-side wrapper becomes `display: contents`, so search and profile are direct grid items). At lg+ the header is unchanged. The footer is left-aligned at tablet width only; mobile stays centred.

</details>

<details><summary>Footer layout breakpoints</summary>

The footer's two blocks (logo/description/social and the link columns) are space-between from 1024px up; 768-1023px is left-aligned; mobile stays centred.

</details>

<details><summary>Nav link stays active on sub-pages</summary>

A header nav link is active when the current path equals its route or starts with it plus "/" — e.g. "News" is highlighted on `/news`, `/news/<category>` and `/news/<category>/<article>`.

</details>

<details><summary>News hover dropdown in the header</summary>

At desktop width the header's "News" link has a hover dropdown listing Cryptocurrency, Artificial Intelligence, Markets & Finance, Technology and Memecoins, each linking to its `/news/<category>` page.

</details>


### Login page and logged-out header pill (2026-10-01)
No auth yet: `CoinState.is_logged_in` is False, so the header pill shows only the avatar and click goes to `/login`. `/login` is a dummy design-only page (`components/login_page.py`): email/password form, Google option (no Apple), no backend. `/signup` is not built yet. Below lg the nav links live in the profile dropdown, so logged-out small-screen users cannot reach them from the header until this is revisited.


### Logged-out avatar dropdown and /signup (2026-10-01)
Below lg the avatar opens the profile dropdown with Log in and Sign up first; at lg+ it links to /login. Login and signup (`components/login_page.py`) are two columns (image left, form right) from 520px up. `/signup` is a dummy form: Full name, Email, Password, Repeat password, terms, Google option; no backend.


### Auth pages layout (2026-10-01)
`/login` and `/signup` are full-screen two-column splits (image left, form right, no card), stacking below 520px. Each password field has its own show/hide toggle.


### Login/signup backend (2026-10-01)
`users` table (Argon2id hashes), `app/services/auth_service.py` (server-side validation, generic login errors, 5-failure/15-minute lockout), reCAPTCHA v2 on both forms (Google test keys by default; set RECAPTCHA_SITE_KEY/RECAPTCHA_SECRET_KEY in .env), `AuthState` handlers, header shows the user name and a Log out row. Session is in-memory per browser session. Forgot password and Google login are not built yet.


### reCAPTCHA v3 (2026-10-01)
Login/signup use invisible reCAPTCHA v3 (hidden token field refreshed by `assets/recaptcha_init.js`, server check of success + action + score >= 0.5). Keys come from `.env` (`RECAPTCHA_SITE_KEY`, `RECAPTCHA_SECRET_KEY`); the site key must list the domain (e.g. localhost) in the reCAPTCHA admin console.


### reCAPTCHA disabled by default (2026-10-01)
Set RECAPTCHA_ENABLED=true in .env to turn the v3 check back on; off by default until the key works for the domain in use.


### Logged-in pill spacing (2026-10-01)
The name/plan stack in the header pill has 0.75em left padding.


### Auth error messages and password-visibility fix (2026-10-01)
Password show/hide resets on every visit to /login and /signup. Errors are specific (email format, password strength items, name characters, already-registered email). The logged-in header pill has 5px padding.


### Persistent login (2026-10-01)
Login survives closing the tab: a random token cookie (`repace_session`, 30 days, SameSite=Strict) maps to a hashed row in `user_sessions`; `CoinState.restore_session` restores the login on every page load; logout deletes the session. Not HttpOnly/Secure yet.


### Remember me (2026-10-01)
Persistent login is opt-in via a "Remember me" checkbox on the login form (unchecked by default). Signup logs in for the tab only.


<details><summary>Floating watchlist star + popup (live prices)</summary>

### 🔧 Feature: floating watchlist star + popup with live prices (2026-10-04 session)
Per explicit request (`el-02/03`), **Global Components**. A 44px circle with a star icon sits directly above the floating logo on every page (`frontend.py::_watchlist_button`); clicking it opens a popup (`_watchlist_widget`, same card style as the chat popup, "View full watchlist" link to `/watchlist`) listing the starred coins in the header-search row design (icon, name + ticker, price over 24h change; click opens the coin). It's mutually exclusive with the chat popup, and the chat popup moved up (bottom 144px) so neither covers the star. **Live prices**: while the popup is open `CoinState.watchlist_live_loop` polls each coin's chart exchange every 3s (`frontend/live_prices.py`: public ticker of the pair `_resolve_chart_symbol` picks — extracted from `_resolve_tradingview_symbol` so the chart and the popup share one resolver; coins without a known pair try MEXC/KuCoin/HTX/Bybit/Binance `{TICKER}USDT`, with a 0.5x–2x sanity check against the synced price; an exchange that errors is skipped for 60s; no match keeps the synced price). Prices go through `_fmt_usd`. TradingView has no price API, so this reads the exchange the chart streams from, a few seconds behind at most. The 24h % change stays the 60s-synced CMC value. **Verified live**: 3 starred coins listed, BTC moved $84,810.18 → $84,806.84 over 7s, star centred over the logo (x=1426), chat/watchlist popups exclusive, zero console errors. In this environment MEXC/KuCoin/Bybit/Binance timed out, so prices came from HTX. Docs: `docs/global-components.md`; Notion pending.

</details>


<details><summary>Triggered price alerts: popups, saved alerts, /alerts page</summary>

### 🔧 Feature: triggered price alerts — sliding popups, saved alerts, /alerts history page (2026-10-04 session)
Per explicit request. **Triggering**: `CoinState.start_alert_watch` (a background event added to the `on_load` of every page that has the floating widgets, guarded to one loop per session) checks the session's active alerts every 4s against live exchange prices (`frontend/live_prices.py`, same source as the watchlist popup; falls back to the synced price). A hit (price >= target for "above", <= for "below") removes the alert, adds it to the history, and shows a popup. **Popup** (`frontend.py::_alert_popups`): fixed, horizontally centred, 104px from the top (just under the header, the red-box spot), width up to 380px; always rendered so it can slide: `top` goes from `-1000px` to `104px` with a 0.7s transition, stays about 60s (re-armed by each new trigger), then slides back to `-1000px` and clears. Several triggers stack vertically (up to 5); each card has its own x that dismisses just that one (the whole stack hides when the last is closed). **Persistence**: new `price_alerts` table (`app/models/price_alert.py`, migration `c5d1e3f4a7b8`, FK to `users` ON DELETE CASCADE; `triggered_at` NULL = active) and `app/services/alert_service.py`. Logged in: alerts are saved on create/delete, loaded at login and on session restore, and marked triggered with the price seen. Logged out: alerts and history stay in the browser session only (lost on server restart). **Profile dropdown**: an **Alerts** row (bell) appears after login and opens the new `/alerts` page (`components/alerts_page.py`, `CoinState.load_alert_history`): the history of triggered alerts (coin, "Rose above/Fell below $X", price at that moment, KL time), newest first, with a "log in to keep your alerts" note for guests. **Floating star button** (`el-08`): back to the plain amber star icon (the three-stars SVG is deleted); the circle still turns white while the popup is open. **Verified live**: a guest ETH alert 0.03% above price triggered within a minute, the popup sat at 104px centred (x=735 of 1470) and slid out ~60s later; a logged-in test account's alert was saved in Postgres, triggered, dismissed with the x, and listed on `/alerts` from the database; the Alerts item appears in the dropdown only when logged in; zero console errors after fixing a hydration warning (a div nested in the callout's `<p>`). Test user deleted (`users`, `price_alerts` empty). **Limits**: alerts only fire while a browser tab is open (no background/email/push delivery); the live check reads public exchange tickers, which were partly blocked from this machine (HTX answered). Docs: `docs/global-components.md`, `docs/single-coin-page.md`; Notion pending.

</details>


<details><summary>/alerts shows active alerts</summary>

### 🔧 Bug fix: /alerts only showed triggered history, so new alerts looked unsaved (2026-10-04 session)
User-reported: after setting a price alert nothing appeared on `/alerts`. The alerts **were** saved (4 active rows in `price_alerts`); the page only listed *triggered* history (empty until a price is hit) — active alerts were visible only on each coin page. `/alerts` now has an **Active alerts** section (all coins, each with icon, name, "rises above / falls below $X", the current price, a link to the coin, and an x that deletes it: `CoinState.active_alerts_all`, `delete_alert_by_id`) above **Triggered history**. Verified live with a temporary account: created an ETH alert on the coin page, it appeared on `/alerts`, the x removed it (DB row gone); test user deleted.

</details>


<details><summary>X search link on Social Insights; Standard badge removed</summary>

### 🔧 Follow-up: "Standard" badge removed; Social Insights "See More" opens an X search for the coin (2026-10-04 session)
Per explicit request (`el-03/05`). **Header**: the grey "Standard" plan badge under the user's name in the logged-in profile pill is removed (`frontend.py::_profile_pill`; now just the name). **Coin page** (`coin_detail.py::_sentiment_column`): Social Insights' "See More" (was an inert `#`) now opens, in a new tab, an X search built per coin by `coin_state._x_search_url` (row field `x_search_url`): `$TICKER OR <chain>:<contract>` for a token, `$TICKER OR <chain>:native` for a coin with no contract — the same query X builds when you pick the coin from its search dropdown. Verified live: `/coin/btc` -> `https://x.com/search?q=$BTC OR bitcoin:native&src=typed_query`; `/coin/pons` -> `$PONS OR robinhood:0x39dbed3a2bd333467115de45665cc57f813c4571`; unit-checked FET -> `$FET OR ethereum:0xaea4…ad85` and SOL -> `$SOL OR solana:native`. **Limits**: X's chain slugs could not be verified live (X redirects logged-out visitors to its login page), so only slugs matching the user's examples / X's own dropdown are mapped (`_X_CHAIN_SLUGS`: ethereum, solana, base, arbitrum, polygon, optimism, robinhood, avalanche); a token on any other chain (e.g. BNB Smart Chain) falls back to a plain `$TICKER` search, and a native coin uses its main-chain name as the slug (`<name>:native`). Add a slug to `_X_CHAIN_SLUGS` once confirmed in X's dropdown. Only the Social Insights link was changed; the separate "View More" link above the X posts section still goes to the coin's own X profile.

</details>


<details><summary>Coin rows and results are real links</summary>

### 🔧 Follow-up: coin rows and results are real `<a href>` links, not click handlers (2026-10-04 session)
Per explicit request (`el-06/07`): anything that moves to another page is now a plain anchor tag, so middle-click, Ctrl/Cmd-click and "open in new tab" work, instead of a Reflex `on_click` (`go_to_coin` / `go_to_coin_from_search`) that ran `window.location.assign`. **Coin table + `/watchlist` table** (`coin_table.py::_name_link`, `coin_href`; `watchlist_table.py`): the icon + name + ticker is an `rx.link(href="/coin/<symbol>")`; a CSS stretched link (`assets/styles.css`: `.coin-row-linked` is `position: relative`, `.row-link::after` covers the whole row) makes the entire row the link; the row's `on_click` is gone. The star cell and the "Also deployed on" chain dropdown carry `.row-interactive` (`z-index: 1`) so they stay separate controls and don't navigate. **Floating watchlist popup rows** (`frontend.py::_watchlist_popup_row`) and **header search results** (`global_search.py::_global_search_result_row`) are now `rx.link` rows. Because a search-result link no longer clears the typed query via a handler, `CoinState.restore_session` (first `on_load` on every page) now clears `global_search_query` on the next page load. Cards that already were links (news cards, Narrative Radar cards, alert rows, "More …" links) are unchanged; remaining handler-based navigations are actions rather than links (post-login/logout redirect, the logged-out avatar's width-dependent redirect-or-dropdown). The existing document click listener (`chain_pills.js`) still turns plain same-origin anchor clicks into full page loads, so behaviour for a normal click is unchanged. **Verified live**: row link `<a href="/coin/btc">`; elementFromPoint on the rank and price cells hits the row link, on the star cell hits the star (not a link); the chain dropdown opens without leaving the page; search results are `<a href="/coin/btc">` etc.; the watchlist popup row is `<a href="/coin/btc">`; zero console errors. (`.to(str)` is needed before `.lower()` on an untyped dict value inside a foreach.)

</details>

<details>
<summary><strong>🕘 Search history (last 5 opened coins)</strong></summary>

Focusing the empty header search box shows a **Recent** list of the last 5 coins opened from the search dropdown (newest first; reopening a coin moves it to the top; no duplicates), in the same row design as results (icon, name, ticker, live price and 24h change). The list is comma-separated `cmc_id`s in the browser's localStorage (`repace_search_history`), so it survives full page reloads but is per browser, not per account. `assets/chain_pills.js` writes it when a `.global-search-result-row` (carries `data-cmc-id`) is clicked — in JS because the click navigates away. `CoinState.global_search_history_raw` (`rx.LocalStorage`) reads it, `global_search_history` builds the live rows (max 5), and `global_search_focused` (input `on_focus`, cleared by `reset_global_search`) opens the dropdown for an empty query only when there is history. Typing shows normal results.
</details>
