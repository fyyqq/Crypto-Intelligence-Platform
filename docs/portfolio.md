# Portfolio (MEXC)

**Route:** `/portfolio` (the Portfolio view of the account area; `/profile` and `/profile/edit-profile` are the Edit view of the same page) and a "Your MEXC" box on every coin page, above Alerts.
**Status:** built 2026-10-16. **Local only, not deployed.** Real data only on the live server, because the MEXC key is linked to the live server's IP and Malaysian ISPs block MEXC by DNS. Locally it is tested with demo data.
**Source:** `app/services/mexc_service.py` (MEXC reads, caching, cost math), `frontend/frontend/state/portfolio_state.py`, `frontend/frontend/components/portfolio_page.py`, styles `.pf-*` in `frontend/assets/styles.css`, table `portfolio_costs` (`app/models/portfolio_cost.py`, migration `c4e6a8b0d2f3`), tests `tests/test_mexc_service.py` + `tests/fixtures/mexc_demo.json`.

## Features

<details><summary><strong>Read-only connection and who can see it</strong></summary>

- The key is a MEXC API key with only Spot **View Account Details** + **View Order Details** ticked, linked to the server's IP (an unlinked key expires after 90 days). `MEXC_API_KEY` / `MEXC_API_SECRET` live only in the server's gitignored `.env`.
- On top of the key's own permissions, `mexc_service._get` signs only GET requests to `_READ_PATHS` (`/api/v3/account`, `/api/v3/openOrders`, `/api/v3/myTrades`). Any other path raises before a request is sent. Nothing in the code can trade, cancel, withdraw or transfer.
- The key and secret are never logged, put in an error, or sent to the browser. Network errors are re-raised `from None` as `MexcError` with a plain message, so no signed URL reaches `logs/error.log`. MEXC error codes map to a fix (e.g. 700006 = "server IP not linked to the key"); any other code shows only "MEXC API error (code N). Details are in the server log." because MEXC's own text can contain the server's IP, and the raw code + message are written to the server log (`mexc_service._log`) instead. Requests use HTTPS only, a 4 s connect / 10 s read timeout and `allow_redirects=False` (a signed request and its API-key header are never forwarded to another address).
- **Nothing stays in the session after logout:** `PortfolioState._clear_portfolio` resets every `pf_*` / `coin_mexc_*` var (found by prefix, so a new var is covered automatically). `CoinState.logout` calls it (through `get_state`), and every loop / refresh also calls it the moment the viewer check fails (logged out, or another account in the tab). Checked end to end in a browser: after logout and after a reload no server frame contains the balances. **Rules for this state:** a public var holds only display strings (never a raw MEXC reply, an id or a credential: `_order_view` no longer sends MEXC's order id), and any raw MEXC data a feature needs must live in a `_`-prefixed (backend-only) var and be emptied in `_clear_portfolio`.
- Only logged-in accounts listed in `MEXC_VIEWER_EMAILS` (comma-separated) get any data. Empty = nobody. Every loop and event checks `mexc_service.can_view(user_email)` on the server. Anyone else sees "Exchange portfolios are not available for this account", and the coin-page box is hidden.
</details>

<details><summary><strong>Dashboard (/portfolio)</strong></summary>

- **Header:** "MEXC Spot · read-only" badge, a "Demo data" badge when the fixture is used, the last successful read time (Kuala Lumpur), and a refresh icon (`refresh_portfolio`, forces a fresh read).
- **Total balance** (all balances x price) with its **24h change** (sum of amount x (price - 24h open)). Four tiles: **Unrealized P/L** (only coins with a known average buy price), **Stablecoins** (and their share of the wallet), **In open orders** (value of locked balances, number of open orders), **Coins held** (plus "small balances": holdings under $1 are folded into one line).
- **Allocation ring:** CSS `conic-gradient` of the 6 biggest holdings + "Others" (Radix step-9 colours, readable in both themes), legend with percentages.
- **Holdings table:** coin (logo + link to `/coins/<slug>` when the site knows the ticker; ties go to the best CMC rank), amount (and how much is in orders), live price (`_fmt_usd`), 24h %, value, average buy price, P/L in $ and %, share bar. Biggest value first.
- **Open orders:** pair, Buy/Sell, type (Limit, Post-only, Stop-limit, Take-profit...), price, trigger price, amount and % filled, remaining value, distance from the market price, time placed.
- **Recent fills:** the 20 latest trades on the coins you hold (time, side, price, amount, total, fee).
- Wide tables scroll inside their card, never the page (checked 1440 / 834 / 375 px, dark and light, no console errors).
</details>

<details><summary><strong>Prices, refresh and caching</strong></summary>

- Prices come from MEXC's own public 24h ticker list (`/api/v3/ticker/24hr`, one call): the USDT pair, else the USDC pair; stablecoins without a pair count as $1.
- One key = one account, so every viewer shares one cache: balances + open orders at most every 20 s (`ACCOUNT_TTL`), prices every 10 s, a coin's trade history every 10 min or as soon as its balance changes (an order filled). The page redraws every 10 s (`portfolio_loop`). It runs while the tab is in the account area, because the sidebar swaps Portfolio/Edit in the browser without a server navigation.
- Open orders: one call for all symbols if MEXC accepts it, else one call per coin held (worth >= $1 or with coins locked). In the per-coin case, USDT locked in buy orders on coins you don't hold can't be listed. The page then says how much and points to that coin's page, where the box asks MEXC for that coin directly.
- On a MEXC error the last good data stays on screen with an amber message above it.
- **Rate limits (HTTP 429, or code 429 in the body):** every MEXC request is paused (`mexc_service._rate`): 20 s the first time (longer if MEXC sends `Retry-After`), doubling on each further 429 up to 5 min, reset by the next good reply. The pause is checked inside `_get` before anything is sent, so the refresh icon (`force=True`) cannot skip it; the page shows "MEXC rate limit reached. Waiting about N s…" and the event is logged as a warning.
- **A failing cycle never stops the loops:** `portfolio_loop` / `coin_mexc_loop` (and the refresh icon and cost saving) catch any unexpected network, database or reply error, write the detail to the server log, show "MEXC data could not be refreshed just now. Retrying shortly." and carry on with the next cycle, keeping the last data on screen.
</details>

<details><summary><strong>Average buy price and profit/loss</strong></summary>

- Worked out from MEXC's trade history of the account (the API keeps about one month), average-cost method (`average_cost`): buys add their USDT cost (a USDT fee adds to it, a fee paid in the coin reduces the coins received), and sells remove coins at the running average.
- Used only when the history covers at least 98% of the holding and no sell was bigger than the coins seen. Otherwise the coin shows "—" (bought earlier or deposited from elsewhere), and the hero notes how many coins lack a price.
- The pencil next to a price opens a dialog to type your own average (e.g. from the MEXC app). It is saved per account in `portfolio_costs` and wins over the history ("set by you"). "Use trade history" deletes it.
</details>

<details><summary><strong>Coin page: "Your MEXC" box (above Alerts)</strong></summary>

- Viewers only. Shows how much of the coin you hold, its value, average buy price and P/L. Below that, every open order on the coin (Buy/Sell, type, price, amount, trigger, distance from the market price), including a buy order on a coin you don't hold yet. "No open MEXC orders for this coin." when there are none. A "Portfolio →" link goes to `/portfolio`.
- `coin_mexc_loop` refreshes it every 15 s and follows the coin when the tab moves to another coin page.
</details>

<details><summary><strong>Setup, local testing, deploy</strong></summary>

- **Server `.env`:** `MEXC_API_KEY`, `MEXC_API_SECRET`, `MEXC_VIEWER_EMAILS=<your login email>`. Then `alembic upgrade head` (creates `portfolio_costs`) and restart. Check that the server IP (`207.180.233.86`) is linked to the key.
- **Local:** MEXC can't be reached from this Mac (the ISP's DNS block, and the key isn't linked to the home IP), so the page shows the MEXC error. To see the UI with made-up data, start Reflex with `MEXC_FIXTURE_FILE=tests/fixtures/mexc_demo.json MEXC_VIEWER_EMAILS=dev-tester@example.com` in front of `reflex run` (process environment overrides `.env`), and restart normally afterwards.
- **Unconfirmed until live:** whether MEXC returns stop-limit / trigger orders placed in the app through `openOrders`, and whether `openOrders` without a symbol is accepted (both handled either way).
</details>
