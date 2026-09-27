# Watchlist

**Route:** `/watchlist` · **Status:** Blank placeholder — shell only, no real content or backend yet
**Source:** `frontend/frontend/frontend.py::watchlist_page` / `_placeholder_page`

Currently renders just the shared header/footer and a "Watchlist / Coming soon" message.

## Entry points that exist (UI only, not wired to anything yet)

<details>
<summary><strong>★ Header profile-menu "Watchlist" row</strong></summary>

In the profile dropdown (click the avatar), listed above the Dark/Light Mode toggle — real navigation to this page.
</details>

<details>
<summary><strong>★ Coin detail page's star icon</strong></summary>

Next to a coin's name on its own `/coin/[symbol]` page — purely decorative right now, no click handler.
</details>

## What building this for real needs

- A state var or database column holding the set of watched coin IDs (per-session vs. persistent-across-sessions is an open decision).
- Wiring the coin-detail star's click to toggle membership in that set.
- Replacing this placeholder with a real filtered view of the coin table scoped to just the watched set.
