# Narrative

**Route:** `/narrative` · **Status:** Blank placeholder — shell only, no real content yet
**Source:** `frontend/frontend/frontend.py::narrative_page` / `_placeholder_page`

Currently renders just the shared header/footer and a "Narrative / Coming soon" message.

**Not to be confused with:** the [Home](./home.md) page's own narrative pill filter (left sidebar) — that's a Home feature that filters the existing coin table, not this page. An early planning note in this project's Notion workspace called this idea the "Narrative & Effected Coin Page" — scope not yet decided.


<details><summary>Narrative Radar page (live)</summary>

### 🔧 Feature: Narrative Radar — homepage section renamed, "More Narratives" link, real `/narrative` page; news strip back to left-to-right (2026-10-04 session)
Per explicit request (`el-24..28`). **News strip**: the right-to-left autoplay is fully reverted (newest card first, original left-to-right drift; `news-slider-rtl` JS branch and `home_crypto_news_rtl` removed) and its "More News" link now goes to `/news/cryptocurrency` (was `/news#cryptocurrency`). **Homepage section**: "Targeted Narrative + Coin" is now **"Narrative Radar"**, with a "More Narratives →" link at the right of the heading row (same style as "More News") to `/narrative`. **`/narrative` page** (the header's Narrative link; previously a blank placeholder): `narrative_alerts.narrative_page_content` lists every AI-targeted Cryptocurrency article (`NewsState.narrative_view`), newest first, 100 cards per page in the same 5/3/2-column grid and first/prev/next/last pagination as a `/news/<category>` page, with a centred "Narrative Radar" title, one-line description and article count; cards are the same text-only ticker + narrative cards as the homepage (full grid width). Title "Repace — Narrative Radar"; on_load loads the news and resets to page 1. Verified live: strip drifts left-to-right (232 -> 367), links correct, header Narrative link opens `/narrative` with 100 cards in 5 columns, "Showing 1–100 of 2254", next page -> 101–200 / Page 2 of 23, zero console errors.

</details>
