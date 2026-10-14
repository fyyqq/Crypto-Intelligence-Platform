# Notifications

**Route:** `/notifications` (login required) · **Status:** Live locally (built 2026-10-12); **not deployed to the live server yet**.
**Source:** `app/models/notification.py`, `app/services/notification_service.py`, `app/services/alert_service.py` (the price-alert hook), migration `c4d7e0f2a6b8`, `frontend/frontend/state/notification_state.py`, `frontend/frontend/components/notifications_page.py`, the bell in `frontend/frontend/frontend.py::_notification_bell`, styles in `frontend/assets/styles.css`, tests in `tests/test_notifications.py`.

One list per account of things the app wants you to know. Today the only producer is price alerts; the table, bell and page are generic so new kinds plug in without changing them.

## Features

<details><summary>Bell icon and popup in the header</summary>

Just the bell icon (lucide `bell`, 22px, `var(--gray-12)`, no circle or border; accent colour on hover), between the search box and the profile pill, shown only when logged in. A red badge on its top-right corner shows the unread count (`9+` above nine). Bell + profile pill are one grid item below 1280px so the header grid keeps search in the middle.

**Click = popup** (like the watchlist popup): a card under the bell (340px wide, anchored to the bell on desktop; pinned under the header at full width below 520px) with the latest 6 notifications (unread dot, image or kind icon, title, time; unread rows tinted), "Mark all read" and an x in its header, and a "View all notifications" link to `/notifications` at the bottom. Clicking a row marks it read and opens its link. It closes on the bell (2nd click), the x, a click anywhere outside (`assets/chain_pills.js`, hidden `#notification-popup-close-trigger`), and on every page load. State: `NotificationState.bell_open` / `recent` / `recent_loading`, events `toggle_popup`, `close_popup`, `page_loaded`.

The unread count is refreshed by `NotificationState.refresh_unread`: when `CoinState.start_alert_watch` starts (every page that runs it, via `page_loaded`), right after any alert triggers, and about once a minute after that, so notifications created elsewhere appear without a reload; the same call also refreshes an open popup's list. The bell appears after the page hydrates (the coin page is slowest).
</details>

<details><summary>Notifications page</summary>

Newest first (up to 200 shown). Each row: unread dot, image (a coin icon, or the kind's icon when there is none), bold title (normal weight once read), a kind badge ("Price alert"), body text and the time (Kuala Lumpur, like the alert history). Unread rows have an accent-tinted background. Clicking a row with a link marks it read and then goes to the link (`NotificationState.open_item`: the link is read from the account's own list server-side and only same-site paths are followed; the anchor carries `data-own-click` so `assets/chain_pills.js` leaves it to the handler, and the click uses `prevent_default`). The x button deletes one row, "Mark all read" and "Clear all" are in the header (Mark all read is disabled when nothing is unread). Empty state: "No notifications yet". Everything is scoped by the server-side user id.
</details>

<details><summary>Price alerts create notifications</summary>

`alert_service.mark_triggered` (called by the alert watch when a price crosses a target) now also adds a `price_alert` notification **in the same transaction** as marking the alert triggered, so each trigger makes exactly one notification (a second open tab loses the atomic update and adds nothing). Title "BTC rose above $1.00" / "ETH fell below $2,000", body "Bitcoin (BTC) crossed above $1.00, now at $82,972.90.", link `/coin/<symbol>`, the coin's CMC icon, tone up (green) or down (red). The caller passes the prices already formatted with `_fmt_usd` (Core rule 1). Alerts that triggered before this feature have no notification (no backfill); they remain in `/alerts` history.
</details>

<details><summary>Server-side alerts, 24/7 (2026-10-13)</summary>

Price alerts no longer depend on an open tab. `frontend/alert_watcher.py` runs as a server lifespan task (`frontend.py::_alert_watch`) every 10s: it loads every account's active alerts (if there are none it makes no calls at all), prices each coin from the shared exchange price list (`price_hub`, plausibility-checked against the stored price) or else the stored hourly CMC price, and triggers crossed alerts through `alert_service.mark_triggered` (atomic, so this and an open tab's own 4s check never both fire). Each trigger creates the notification and goes to the external channels. Verified with no browser open: an armed, already-crossed BTC alert fired within 25s; a far-away one stayed active. An open tab still shows its popup and voice for alerts it sees itself.
</details>

<details><summary>Telegram delivery (2026-10-14, local only, not deployed)</summary>

Every notification of an account that connected Telegram is also sent by our own bot (`TELEGRAM_BOT_TOKEN` from @BotFather, in `.env` / `Settings.telegram_bot_token`; `PUBLIC_SITE_URL` is the base for the "Open on Repace" link, default the live site). Separate from the news listener's user session. Source: `app/services/telegram_notify_service.py`, column `users.telegram_chat_id` (migration `e9a2c4b6d8f0`), card on `/notifications` (`_telegram_card`, `NotificationState.connect_telegram` / `watch_telegram_link` / `disconnect_telegram` / `test_telegram`), channel registered in `frontend.py` via `register_channel(send_channel)`, tests `tests/test_telegram_notify.py`.

**Connecting:** "Connect Telegram" makes a one-time code (10 min, in memory) and opens `t.me/<bot>?start=<code>`; the user presses Start; a background event polls the bot's `getUpdates` every 3s for up to 2 minutes, links the chat id to the account and the bot confirms in the chat. Without the command listener (local) polling is on demand only; with it (live) the listener does the linking and the card just waits for the chat id. Only private chats link. "Send test" and "Disconnect" appear once connected. Messages: coloured dot by tone, bold title, body, link. A failing send is logged and never blocks the notification. 

**`/view_all_command`** (also `/view_all_commands`, `/help`; first entry of the bot menu) lists every command, marking the parts you fill in as `{coin}` and `{date}`. It needs no connected account and shows no private data. Keep `commands_overview()` in `telegram_notify_service.py` in sync when adding a command.

**`/site_health`** (2026-10-14, a command only: nothing is sent automatically) replies with one message on whether the site's data is alive, worst first, each line with a 🟢/🟠/🔴 dot and a summary line ("2 problems, 1 warning"). Source: `app/services/site_health_service.py` (one `check_*` function per row; a check that itself fails is reported as a red row, never hides the others), tests `tests/test_site_health.py`. Checks: database reachable (ms); **price snapshots** (feed the Gainers & Losers boards; newest age, green <= 75 min, orange <= 3 h, red beyond); **exchange prices** (refreshes the shared list, shows symbols, age, and any source in back-off); **CoinMarketCap** (credits left from `/v1/key/info`, which costs none, red when used up, plus whether the last hourly sync failed and its error); **news** (newest article age, last successful pipeline run, a run stuck "running" > 90 min); **news listener** (`pgrep` for the Telegram listener process); **price alert watcher** (in-process heartbeat from `alert_watcher.run_forever` via `app/services/heartbeat.py`, plus the active alert count); **server** (disk free, load per core, memory available on Linux); **daily Telegram messages** (last sent day of the 24H board and the index, orange if not sent by ~09:00 KL). The in-process rows (exchange prices, alert watcher) describe the server whose Reflex process answers the command, i.e. live; run from a script they show as red/orange. Linked chats only. Not built: automatic "something broke" pushes (only the command exists).

**Bot commands** (`handle_message`, listener `run_poller`, a lifespan task in `frontend.py`): `/alerts` lists the account's active alerts grouped by coin, `/alert ETH` (also `/alert $ETH`, `/alert@bot ETH`) lists the active alerts of one coin; `/help`; `/command1` still works as an old alias of `/alerts`. Prices go through `_fmt_usd` (Core rule 1, set via `set_price_formatter`). Only private chats of a linked account are answered; others get "not connected". At listener start the menu is set with `setMyCommands` (`COMMANDS`), replacing whatever was set in @BotFather. **The listener runs only where `TELEGRAM_BOT_POLLING=true` (live)**: Telegram allows one `getUpdates` consumer per bot token, so local dev leaves it off (a second consumer would get 409 and steal updates); use a separate dev bot token locally if commands must be tested there. Gainers & Losers commands (`/gainers_losers_24h`, `_7d`, `_1m`) and the automatic digest live in `app/services/telegram_digest_service.py` (see `docs/gainers-losers.md`); its menu entries are merged by `menu_commands()`. To add a command: add it to `COMMANDS`, a branch in `handle_message`, and a test. Sending notifications needs no listener, only the token. All Bot API calls are forced to IPv4 (`_sync_client` / `_async_client`): from the live server Telegram's IPv6 hangs or times out while IPv4 answers in ~0.1s (found 2026-10-14, when `/alerts` replies and polls were timing out).

WhatsApp (Cloud API / Twilio) is still not built; it would plug into the same `register_channel` hook.
</details>

<details><summary>How to add a new kind of notification</summary>

1. Add a row to `notification_service.KINDS` (`kind: (label, lucide icon)`). The page picks the icon up automatically (`rx.match` built from `KINDS`).
2. Where the event happens, call `notification_service.notify(user_id, kind, title, body=, link_url=, image_url=, tone="up"|"down"|"info")` (own transaction), or `add_in_session(db, ...)` to join the caller's transaction. An unknown kind or tone raises, so typos fail loudly.
3. Nothing else changes: the bell badge and the list pick it up (badge within a minute, or on the next load of the page).

Ideas not built: followed-news alerts, watchlist movers, Gainers & Losers milestones, system announcements (the `system` kind exists for these).
</details>

<details><summary>Storage and retention</summary>

`notifications` table: `user_id` (FK to users, cascade delete), `kind`, `title`, `body`, `link_url`, `image_url`, `tone`, `created_at`, `read_at` (NULL = unread), indexed on (`user_id`, `created_at`). Each `notify` prunes that account's list: anything older than 90 days, then everything beyond the newest 500.
</details>
