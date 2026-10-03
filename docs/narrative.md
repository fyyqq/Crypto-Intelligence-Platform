# Narrative

**Route:** `/narrative` · **Status:** Blank placeholder — shell only, no real content yet
**Source:** `frontend/frontend/frontend.py::narrative_page` / `_placeholder_page`

Currently renders just the shared header/footer and a "Narrative / Coming soon" message.

**Not to be confused with:** the [Home](./home.md) page's own narrative pill filter (left sidebar) — that's a Home feature that filters the existing coin table, not this page. An early planning note in this project's Notion workspace called this idea the "Narrative & Effected Coin Page" — scope not yet decided.


<details><summary>Narrative Radar page (live)</summary>

### 🔧 Feature: Narrative Radar — homepage section renamed, "More Narratives" link, real `/narrative` page; news strip back to left-to-right (2026-10-04 session)
Per explicit request (`el-24..28`). **News strip**: the right-to-left autoplay is fully reverted (newest card first, original left-to-right drift; `news-slider-rtl` JS branch and `home_crypto_news_rtl` removed) and its "More News" link now goes to `/news/cryptocurrency` (was `/news#cryptocurrency`). **Homepage section**: "Targeted Narrative + Coin" is now **"Narrative Radar"**, with a "More Narratives →" link at the right of the heading row (same style as "More News") to `/narrative`. **`/narrative` page** (the header's Narrative link; previously a blank placeholder): `narrative_alerts.narrative_page_content` lists every AI-targeted Cryptocurrency article (`NewsState.narrative_view`), newest first, 100 cards per page in the same 5/3/2-column grid and first/prev/next/last pagination as a `/news/<category>` page, with a centred "Narrative Radar" title, one-line description and article count; cards are the same text-only ticker + narrative cards as the homepage (full grid width). Title "Repace — Narrative Radar"; on_load loads the news and resets to page 1. Verified live: strip drifts left-to-right (232 -> 367), links correct, header Narrative link opens `/narrative` with 100 cards in 5 columns, "Showing 1–100 of 2254", next page -> 101–200 / Page 2 of 23, zero console errors.

</details>


<details><summary>Badge row reversed, chain dropdown click fix, Problem It Solves</summary>

### 🔧 Follow-up: Narrative Radar badge row reversed; chain dropdown no longer opens the coin page; "Problem It Solves" in AI summaries (2026-10-04 session)
Per explicit request (`el-29..31`). **Narrative Radar cards** (homepage + `/narrative`): the badge row is `row-reverse` — time on the left, narrative + ticker badges on the right. **Coin table chain dropdown** (`coin_table._chain_badge`, also used by the `/watchlist` table): the popover is wrapped in a box with `on_click=rx.stop_propagation`, so opening the "Also deployed on" dropdown or clicking inside it no longer triggers the row's navigate-to-coin click (Radix portals the content, but React events still bubble through the component tree). The narrative badge has no dropdown, so this was the only one. **AI Summarizations** (`business_summary_service._SYSTEM_PROMPT`): now 3-4 paragraphs, the first always titled "Problem It Solves" (what problem/gap existed and why the project was created; meme coins say plainly they were made for fun/community). Existing summaries without that section and written before the change (`_PROBLEM_SECTION_SINCE`, 2026-10-03 18:30 UTC) are regenerated once on the next visit to the coin's page; newer ones are never force-refreshed, so a model that skips the section can't cause a regeneration loop. **Not yet visible**: OpenRouter's free daily quota (50 requests) is still exhausted until 08:00 KL; until then the old summary keeps showing (generation failures fall back to the cached text). Verified live: badge row computed `row-reverse` with time leftmost; clicking the chain dropdown and inside it stayed on `/`; service imports and app compiles.

</details>
