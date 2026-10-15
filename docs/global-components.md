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

News / Narrative / Chains / Tools / Memecoin (`/memecoin`, a blank "Coming soon" page since 2026-10-15) — each a real page (see [News](./news.md), [Narrative](./narrative.md), [Chains](./chains.md), [Tools](./tools.md)); [Gainers & Losers](./gainers-losers.md) has no link of its own since 2026-10-14: it is reached from the Tools dropdown and the `/tools` landing card (the Tools link stays highlighted on `/gainers-losers`, `_nav_link(also_active=...)`), not an anchor into another page. **News** and **Tools** have a hover dropdown (`frontend.py::_dropdown_nav_item`, entries in `_NAV_DROPDOWNS`: the news categories, and the tools from `TOOL_PAGES`: Market Indicators, Market Charts, Gainers & Losers, Crypto Calendar and CPI & FOMC); the link itself still goes to `/news` / `/tools`. Below 1280px the nav lives in the profile dropdown as plain links (no sub-entries). The link matching the current route (or a sub-route, e.g. `/tools/market-charts`) highlights in the accent color. Visible at every screen width; below roughly 480px the row becomes a horizontal swipe rather than clipping any link permanently, since all four genuinely don't fit next to the logo and search/profile controls at that width.
</details>

<details>
<summary><strong>🔍 Global search</strong></summary>

Always-visible (70px to 240px depending on screen width), transparent-background search bar, left of the profile pill. A "/" keyboard shortcut focuses it, hidden on touch/phone widths since there's no physical keyboard there. Typing shows a CoinMarketCap-style autocomplete dropdown: up to 5 coin matches by default (icon, name — truncated with an ellipsis rather than wrapping if too long — ticker, real price shown above a smaller 24h-change line), a "Show more" expander, an empty state, and a real "Articles" section heading with an honest "News search isn't available yet" placeholder, since no news-search backend exists. An "x" replaces the "/" badge once there's a query, clearing the field and closing the dropdown in one click. Also closes on a real click anywhere outside it.
</details>

<details>
<summary><strong>⚡ Instant clicks (assets/instant_ui.js, 2026-10-13)</strong></summary>

Every click in a Reflex app is a round trip to the server (~0.35s+ from Malaysia to the live server in Germany) before anything visibly changes. `assets/instant_ui.js` (loaded on every page via `head_components`) gives the first visible reaction in the browser instead, while the server event still runs and confirms it. Measured with 350 ms of simulated latency:
- **Table** (page numbers/arrows, narrative + chain pills, sortable headers `.sortable-th`, rows-per-page `.rows-per-page-select`, the table search): the clicked pill/page turns active and the skeleton (`tbody.skel-rows`, always rendered hidden) shows in ~5-12 ms via `.coin-table-wrap.table-loading`, until the new rows arrive (at least 300 ms, the old skeleton duration).
- **Watchlist stars** (`.wl-star`): fill flips in ~5 ms (`svg.wl-star-force-on/off`), dropped once the server re-renders the star.
- **Popups**: watchlist (`.watchlist-fab` -> `.watchlist-popup`) and notification bell (`.notification-bell` -> `.notification-popup`) are always rendered and shown by an inline `style.display`, so the script opens/closes them in ~2-120 ms; the bell also closes on a click outside.
- **Header search**: on first focus the browser loads `/api/coin-index` (every coin's id, symbol, name, stored price/24h, by market cap; ~185 KB gzipped, cached 5 min; built from the shared coin list in `frontend.py::_coin_index`) and shows the top 5 matches as you type (`.gs-instant`); the server's live results replace them as soon as the dropdown's `data-q` matches the box. The server match list is server-only now (`_global_search_matches`; it used to send every match's full row on each keystroke).
</details>

<details>
<summary><strong>🔐 Login wall and Google sign-in (2026-10-14)</strong></summary>

**Every page needs a login**, always (not only in private mode): `CoinState.restore_session` sends a logged-out visitor to `/login` (also `/signup` when sign-up is open, i.e. no `ALLOWED_LOGIN_EMAILS`), and `_header_bar` covers the page until then. Logging out lands on `/login`. Verified: after Log out, `/`, `/coin/btc`, `/gainers-losers`, `/tools`, `/news`, `/watchlist`, `/notifications` all go to `/login` with nothing shown first.

**Google sign-in**: `/login` and `/signup` show Google's own "Continue with Google" button, rendered by the official Google Identity Services library (`https://accounts.google.com/gsi/client`) through `assets/google_login.js` (popup mode). The ID token Google returns is POSTed to `/api/auth/google` (`frontend.py::_google_login`: same-site Origin + JSON only), verified by `app/services/google_auth_service.py` with `google.oauth2.id_token.verify_oauth2_token` (Google's signature, expiry, issuer, and audience = `GOOGLE_CLIENT_ID`), and accepted only for a verified email that is allowed (`ALLOWED_LOGIN_EMAILS`) and already has an account (never creates one). Success sets the same 30-day `repace_session` cookie as "Remember me", so the next page load is logged in. `GOOGLE_CLIENT_SECRET` is not used: ID tokens are verified with Google's public keys and the client ID. The browser gets only the public client ID (`/api/auth/google/config`). The button's iframe has `color-scheme: light` (`#google-signin-btn iframe` in `styles.css`): without it the browser paints an opaque white box (Google's ~10px glow margin) around the button on the dark login panel; verified by pixel sampling (edges match the panel colour in dark, light and at 375px). Google Cloud setup needed: a "Web application" OAuth client whose Authorized JavaScript origins include `http://localhost:3000`, `http://localhost` and `https://repace.fyqqflow.com`.
</details>

<details>
<summary><strong>🔒 Private mode (login gate)</strong></summary>

When `ALLOWED_LOGIN_EMAILS` is set (live server: the owner's account only), every page sends a logged-out visitor to `/login`, covered by a full-screen spinner until the redirect so nothing shows first; sign-up is closed and its link hidden; any other account gets "Invalid email or password." Unset locally, so local dev stays open (with the dev auto-login). Measured: the cover lifts ~0.2s after load for the allowed account.
</details>

<details>
<summary><strong>🔔 Notification bell</strong></summary>

Logged-in only: a bare bell icon (no circle) between the search bar and the profile pill with a red unread-count badge. Click opens a popup with the latest 6 notifications and a "View all notifications" link to `/notifications`. Details and how it is fed: [Notifications](./notifications.md).
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


<details><summary>Spoken price alerts (Gemini voice)</summary>

### 🔧 Feature: triggered alerts are spoken aloud by a Gemini voice (2026-10-05)
When `start_alert_watch` marks an alert triggered in the DB (`alert_service.mark_triggered` returns True only for the first tab that marks it, so other open tabs stay silent), it yields `CoinState.speak_alert("<Coin> (<SYM>) crossed above/below $X, now at $Y")`. That background event calls `app/services/alert_voice_service.py::generate_alert_voice`: `gemini-2.5-flash` writes a witty line under 15 words using the fixed system instruction, then `gemini-2.5-flash-preview-tts` voices it (`gemini-2.5-flash` itself has no audio output). The voice defaults to `Puck` (`GEMINI_VOICE_NAME`), and the models are set by `GEMINI_TEXT_MODEL` / `GEMINI_TTS_MODEL` in `.env`. The key is `GEMINI_API_KEY`, read through `app/core/config.py`. The raw 24 kHz 16-bit PCM is pushed as base64 through `rx.call_script` to `window.repacePlayAlertVoice` (`frontend/assets/alert_voice.js`, loaded on every page via `rx.App(head_components=[rx.el.script(...)])`; `rx.script` wraps it in Helmet, where it never runs). The Web Audio API plays it, with back-to-back queueing so simultaneous alerts don't overlap. The browser autoplay rule means the shared AudioContext unlocks on the first click or keypress on the site; clips that arrive before that are queued and play on the first interaction. Once unlocked, speech keeps playing while the tab is in the background (the server-side watch loop runs as long as the tab's websocket is open). If Gemini fails, the alert still pops up silently, and the error is logged.

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

<details>
<summary><strong>🎨 Light-mode background</strong></summary>

In light mode the page background is `#f5f5f7` instead of Radix's plain white. `assets/styles.css` overrides `--color-background` / `--color-page-background` and the background of `html.light .radix-themes` and `body`. Dark mode is unchanged. The stylesheet is copied at build time, so restart Reflex after editing it.
</details>

<details>
<summary><strong>🌗 Light/dark theme rule (white cards, readable AI text)</strong></summary>

In light mode the page is `#f5f5f7` and every card/section is white: `assets/styles.css` overrides Radix's `--gray-a2` (the near-transparent card surface) and `--gray-2` (popups, header, tables) to `#fff` under `html.light .radix-themes`. Build cards with those variables, not a fixed colour. Text on themed surfaces must never be hardcoded white/black — use `var(--gray-12)` (main) or `var(--gray-11)`/`color_scheme="gray"` (secondary). AI-generated text (coin AI Summarizations, news-reader AI summary) used `color="white"` and was invisible in light mode; it now uses `var(--gray-12)`. Fixed whites remain only on surfaces that are dark/coloured in both modes (royalblue badges, active accent pills, image overlays, toasts, the login/signup pages).
</details>

<details>
<summary><strong>🪵 Error log (`logs/error.log`) and the "An error occurred" toast (2026-10-13)</strong></summary>

The toast "An error occurred. Contact the website administrator." is Reflex's own production message: it appears when a Python event handler (a `State` method) raises. Visitors never see the real error. `frontend/frontend/error_log.py` replaces Reflex's default handlers (wired in `rx.App(backend_exception_handler=..., frontend_exception_handler=...)`): each exception is appended with its full traceback to `logs/error.log` at the repo root (UTC timestamps, 1 MB x 5 rotating files, gitignored) and still printed to the process output. The toast now also shows `Reference: <8 hex chars>`; that id is in the matching log entry, so a visitor's report can be found with `grep <ref> logs/error.log`. On the live server: `ssh deploy@repace.fyqqflow.com 'tail -n 80 ~/repace/logs/error.log'` (relative to where Reflex is started: it is the repo root, not `frontend/`). Only exceptions inside Reflex event handlers land here; a crash/restart of the whole process (e.g. the nightly restart) is in `journalctl -u repace-reflex.service`.
</details>

## Page loading screen (2026-10-15)

Every page load or reload (links are full reloads) first shows the Repace 3D logo GIF (`assets/loading-logo.gif`, 540x400, ~4 MB, cached by the browser) on a `#111013` screen for **at least 5 seconds counted from the start of the navigation**, and until the browser's `load` has finished, then fades out (`assets/loading_overlay.js`, first in `head_components`; it lives on `<html>` outside the React root, hard-capped at 20 s). The logged-out login cover (`private-mode-cover`) uses the same GIF instead of the spinner. To change the time, edit `MIN_MS` in the script.

## Alerts page and watchlist star (2026-10-15)

`/alerts` now lists only **active** alerts: the "Triggered history" section, `CoinState.alert_history`, `load_alert_history` and `alert_service.list_history` were removed. A triggered alert is **deleted** (`alert_service.mark_triggered` removes the row and adds the notification in the same transaction; a second tab or the 24/7 watcher deletes 0 rows and adds nothing), so no inactive rows stay in `price_alerts`; the bell notification is the record. Migration `f2a4c6e8b0d1` deletes the triggered rows that already existed (not reversible). **Star clicks:** the watchlist page's star cell lacked the `row-interactive` class, so the row's stretched link overlay (`.row-link::after`) sat over it and a click opened the coin page; it now has the class, and `.coin-row-linked .wl-star` also gets `position: relative; z-index: 2` in `styles.css` for every table. The narrative / chain search boxes have `padding-left: 5px` (`.filter-search input`).

## Profile page (2026-10-15)

The profile dropdown has **Profile** as its first row (logged in only); it opens `/profile` (`components/profile_page.py`, `state/profile_state.py`, `app/services/profile_service.py`, tests `tests/test_profile_service.py`). Layout: a full-width **banner** (150 / 190 / 230 px high by width, a gradient when none is set) with a pencil to replace it, the **profile picture** overlapping it with its own pencil, the name and e-mail, a "Save changes" button (full width on phones), then **Personal details**: first name, last name, mobile number, **Email ID (read-only, filled from the login, disabled)** and address, two columns from 768 px and one on phones, theme tokens only (checked dark and light at 1440 / 834 / 375 px). **Database:** migration `a7c9e1b3d5f2` adds `users.phone`, `address`, `avatar_url`, `banner_url` (all nullable); the name is `users.full_name` split into first/last at the first space and saved back as "first last". Validation (server side, `profile_service.validate`): first name required, names <= 40 characters, mobile = digits, spaces, `+ ( ) -` (6-30 characters) or empty, address <= 300; a rejected save changes nothing and each message shows under its field. **Pictures:** the pencils open the computer's file picker (`rx.upload`, auto-upload on selection); PNG, JPG, WebP or GIF up to 5 MB, checked with Pillow (real image, <= 40 MP, EXIF rotation applied), the avatar is cropped to a 512 px square and the banner to 4:1 (1600x400, never enlarged past its own width), saved as WebP in `user_uploads/profile/` (gitignored, created on start) under a random name, the previous file deleted; they are served live from disk at `/user_uploads/...` (Starlette mount, like `/telegram_media`). The header's avatar circle shows the picture (`CoinState.user_avatar`, loaded at session restore). **Live nginx note:** nginx's default `client_max_body_size` is 1 MB, so uploads above that need `client_max_body_size 8m;` in the `server` block of `/etc/nginx/sites-enabled/repace.fyqqflow.com` and `sudo systemctl reload nginx` (needs sudo; the app itself allows 5 MB).
