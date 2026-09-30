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
