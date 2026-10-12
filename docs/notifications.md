# Notifications

**Route:** `/notifications` (login required) · **Status:** Live locally (built 2026-10-12); **not deployed to the live server yet**.
**Source:** `app/models/notification.py`, `app/services/notification_service.py`, `app/services/alert_service.py` (the price-alert hook), migration `c4d7e0f2a6b8`, `frontend/frontend/state/notification_state.py`, `frontend/frontend/components/notifications_page.py`, the bell in `frontend/frontend/frontend.py::_notification_bell`, styles in `frontend/assets/styles.css`, tests in `tests/test_notifications.py`.

One list per account of things the app wants you to know. Today the only producer is price alerts; the table, bell and page are generic so new kinds plug in without changing them.

## Features

<details><summary>Bell icon in the header</summary>

A circular bell button (lucide `bell`, the same icon as the Alerts menu item) between the search box and the profile pill, shown only when logged in. 44px (36px below 520px). Clicking it is a real link to `/notifications`. A red badge shows the unread count (`9+` above nine). The count lives in `NotificationState.unread` and is refreshed by `NotificationState.refresh_unread`: when `CoinState.start_alert_watch` starts (every page that runs it), right after any alert triggers, and about once a minute after that, so notifications created elsewhere appear without a reload. Bell + profile pill are one grid item below 1280px so the header grid keeps search in the middle. The bell shows up after the page hydrates (the coin page is slowest).
</details>

<details><summary>Notifications page</summary>

Newest first (up to 200 shown). Each row: unread dot, image (a coin icon, or the kind's icon when there is none), bold title (normal weight once read), a kind badge ("Price alert"), body text and the time (Kuala Lumpur, like the alert history). Unread rows have an accent-tinted background. Clicking a row with a link marks it read and then goes to the link (`NotificationState.open_item`: the link is read from the account's own list server-side and only same-site paths are followed; the anchor carries `data-own-click` so `assets/chain_pills.js` leaves it to the handler, and the click uses `prevent_default`). The x button deletes one row, "Mark all read" and "Clear all" are in the header (Mark all read is disabled when nothing is unread). Empty state: "No notifications yet". Everything is scoped by the server-side user id.
</details>

<details><summary>Price alerts create notifications</summary>

`alert_service.mark_triggered` (called by the alert watch when a price crosses a target) now also adds a `price_alert` notification **in the same transaction** as marking the alert triggered, so each trigger makes exactly one notification (a second open tab loses the atomic update and adds nothing). Title "BTC rose above $1.00" / "ETH fell below $2,000", body "Bitcoin (BTC) crossed above $1.00, now at $82,972.90.", link `/coin/<symbol>`, the coin's CMC icon, tone up (green) or down (red). The caller passes the prices already formatted with `_fmt_usd` (Core rule 1). Alerts that triggered before this feature have no notification (no backfill); they remain in `/alerts` history.
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
