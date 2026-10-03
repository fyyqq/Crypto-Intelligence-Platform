# News

**Routes:** `/news`, `/news/[news_category]/[article_slug]` · **Status:** Live
**Source:** `app/services/news_pipeline.py` (RSS/Google News ingestion), `app/services/telegram_pipeline.py` (Telegram group ingestion), `frontend/frontend/state/news_state.py`, `frontend/frontend/components/news_page.py`, `frontend/frontend/components/news_detail.py`, `frontend/frontend/frontend.py`

A real, ingested news feed — grouped by news type (Cryptocurrency, Artificial Intelligence, Markets & Finance, and Technology), each category its own independently-paginated section. Telegram posts are mixed into the same category sections as web articles (merged on 2026-09-30, per explicit request) and marked with a "Telegram News" badge. Every card still identifies its real publisher.

**Not to be confused with:** the [Home](./home.md) page's own "All News" and "Targeted Narrative + Coin" sliders (static placeholder headlines, unrelated to this page's real data) — those stay exactly as they were, untouched by this feature.

## Features

<details>
<summary><strong>📰 Zero-API-key ingestion pipeline</strong></summary>

`app/services/news_pipeline.py` — a standalone script (no imports from the rest of this repo; genuinely copy-out-and-run-anywhere), runnable manually and invoked automatically by this app's scheduler when the FastAPI backend is running. Two ingestion paths, both writing into one `news_articles` table:

1. **Real-time RSS** (`feedparser`) — 12 feeds across four categories: Tech (TechCrunch, The Verge, MIT Technology Review, Ars Technica), Crypto (Cointelegraph, CoinDesk, The Block, Decrypt), AI (WIRED's own AI-tagged feed, CNBC), and Finance (CNBC, MarketWatch). The originally-requested "Artificial Intelligence News" (artificialintelligence-news.com) was swapped for WIRED — confirmed live that site now sits behind a hard captcha wall (SiteGround's `SG-Captcha`) that returns a 176-byte redirect stub to every scripted request regardless of User-Agent, so it can never yield real articles. Other candidates tried and rejected: CryptoSlate (403 bot-blocked), aimagazine.com (no feed at any standard path), Reuters (no public RSS feed exists), Bloomberg/WSJ (feeds respond but individual articles are hard-paywalled, so they'd only ever yield a title/link/date with no real body).
2. **Dynamic 90-day historical lookback** (`pygooglenews`) across 18 `(category, query)` pairs (e.g. Crypto: cryptocurrency/bitcoin/eth/defi/stablecoin/web3/crypto regulation/crypto ETF; AI: artificial intelligence/machine learning/generative AI/AI regulation; Finance: global stock market/federal reserve interest rates/inflation report; Tech: big tech layoffs/semiconductor industry). The leading category tag (not the raw query text) is what gets stored as `category_or_query`, so `NewsState`'s own normalization can reliably bucket every query even when the query text itself doesn't contain an obvious keyword (e.g. "eth"/"defi" don't contain "crypto"). The search window's start/end dates are computed fresh from `datetime.date.today()` on every run — never a hardcoded date string — so the same trailing 90-day window moves forward automatically whether the script runs today, next week, or next year. Capped at 100 results per query per run (Google's own top-relevance ranking) — a later run naturally surfaces different results since already-seen URLs are skipped.

Every article's full body text is extracted with `trafilatura` (free, local, no API key — strips nav/ads/cookie banners down to the real article text).
</details>

<details>
<summary><strong>🖼️ Multi-tier real image sourcing</strong></summary>

Every article gets an `image_url` only when the publisher exposes a real article image. The priority is: (1) the outlet's declared RSS featured image (`media_content`/`media_thumbnail`), or the article page's own `og:image`/`twitter:image`; (2) the article's first real in-content image, extracted via `trafilatura`'s `include_images` pass and filtered to drop author headshots, avatars, and site icons. Generic online image search is deliberately not used because it can be unrelated to the headline. A card with no verified publisher image receives one of three user-supplied local visuals from its own category: Cryptocurrency (including Crypto Telegram) uses `crypto-news-fallback-image/`; Artificial Intelligence, including Technology, uses `ai-news-fallback-image/`; Markets & Finance (and uncategorized articles) uses `financial-market-news-fallback-image/`. A URL hash chooses a stable image within that category's three-image set, avoiding refresh flicker. If a stored publisher URL later becomes broken or blocked, a delegated browser error handler immediately swaps that card to the same category-matched fallback. Every image is contained in a fixed, non-shrinking 160px frame, so broken/slow/external and local fallback images keep identical card geometry. The local fallback is never persisted to `news_articles`, so a real publisher image can still replace it whenever one becomes available.

Older rows created before `image_url` existed are completed on demand rather than blocking the site behind one long full-archive backfill. `NewsState.load_news` enriches the first visible 12-card page of every regular-news section; every previous/next/first/last pagination action and source-filter change enriches its destination page in a background event. Existing real publisher images are reused from Postgres first. Missing images get one fast, bounded, concurrent lookup against the article's own page. Successful upgrades are persisted; unavailable publisher images and Telegram posts use the UI-only local fallback visuals.
</details>

<details>
<summary><strong>🔗 Google News redirect decoding</strong></summary>

A dependency beyond the pipeline's originally-specified library list, but a required one: `pygooglenews`'s own RSS links point to a Google redirect page (`news.google.com/rss/articles/<token>`), not the real publisher URL — confirmed live that page is a client-side-rendered SPA with no HTTP redirect or meta-refresh anything could follow. `googlenewsdecoder` (a small, actively-maintained package) resolves the real URL by replaying Google News's own internal decode request. Without it, every Google-News-sourced row would have an empty body and a URL that just opens Google's own JS shell instead of the article.
</details>

<details>
<summary><strong>🛡️ Idempotency, resilience, and permanent archival</strong></summary>

- **Idempotent**: every candidate URL is checked against `news_articles` *before* the (expensive) full-page fetch + extraction — a re-run only ever does real work for genuinely new articles. A `UNIQUE` constraint on `url` plus a caught `UniqueViolation`/`IntegrityError` is the race-condition backstop on top of that pre-check.
- **Resilient**: the page-fetch + `trafilatura.extract` step is wrapped in a broad try/except — a Cloudflare wall, hard paywall, dead link, or timeout logs a warning and moves on to the next article rather than stalling the run. The article's title/URL/date are still recorded even when body extraction specifically fails (confirmed live: several real Google News results — RAND, Nature, The Economist, AP News, Reuters — hit exactly this path during a real run, all correctly skipped-with-a-null-body rather than crashing anything).
- **Polite crawling**: a 1-second delay between every page fetch.
- **Append-only, forever**: this module contains no `DELETE`, `TRUNCATE`, or any other data-expiration statement anywhere, by design. An article that scrolls past the 90-day lookback window as time moves forward isn't removed — it just stops being re-discovered by future searches, and stays in the database as permanent history.
</details>

<details>
<summary><strong>🗄️ Dual-database configuration</strong></summary>

Controlled by two environment variables read once at import: `NEWS_DB_BACKEND` (`"postgres"`, the default, or `"sqlite"`) and `NEWS_DATABASE_DSN` (a libpq DSN string for Postgres, or a file path for SQLite — defaults to this project's own local dev Postgres, or `news_fallback.db`, respectively, if unset). Schema (`news_articles`: `id`, `source_type`, `source_name`, `category_or_query`, `title`, `url` UNIQUE, `published_date`, `full_body_text`, `image_url`) is created with `CREATE TABLE IF NOT EXISTS` on every run, with an `ALTER TABLE ... ADD COLUMN` upgrade path for `image_url` specifically (added after the table already existed in real usage) — no separate migration step needed, and safe to run repeatedly. `source_name`/`image_url` are the two columns added beyond the feature's originally-specified schema — `source_name` is the real display outlet (e.g. "TechCrunch", or Google News's own attributed "Reuters"/"SEC.gov"/...), needed so the `/news` page can group by real publisher rather than only the coarse `source_type` ("rss"/"google_news"/"telegram") or the raw search query text.

Uses raw `psycopg2`/`sqlite3` directly, not this project's own SQLAlchemy models — a deliberate, genuinely standalone script per its own spec, not a service coupled to the rest of this app's ORM layer.
</details>

<details>
<summary><strong>📋 The page itself — category-grouped, paginated grid</strong></summary>

`NewsState` (Reflex) reads `news_articles` directly from the same Postgres database the pipeline writes to — via `app.core.database.SessionLocal`, the same "reach into the real Postgres app DB directly" pattern `CoinState`'s own background refreshers already use elsewhere in this app (raw SQL `SELECT`, not an ORM model, since the pipeline itself doesn't define one either).

- **Strict rolling-90-day display window**: `NewsState`'s own fetch query now filters `WHERE published_date >= NOW() - INTERVAL '90 days'` at read time, on top of the pipeline's own 90-day *search* window at ingestion time. These aren't redundant — a small number of stored rows (3, confirmed live) sit outside 90 days despite the ingestion-time search constraint (Google News occasionally surfaces a stale/mis-dated result for a query), so the display-time cutoff is what actually guarantees "only the last 90 days" on screen, independent of what's sitting in the permanent archive.
- `NewsState` reads each article's stored `category_or_query` alongside its publisher, then normalizes it into Cryptocurrency (`Crypto`/`cryptocurrency`), Artificial Intelligence (`AI`/`artificial intelligence`), Markets & Finance (`global stock market`), or Technology (`Tech`). A publisher-based fallback covers future unclassified RSS rows without changing stored data.
- Sections appear in a fixed reader-oriented order: Cryptocurrency, Artificial Intelligence, Markets & Finance, Technology, then General News if an unclassified article ever arrives. Each section is a responsive grid (1 column on phones, 2 on tablets, 3 on tablets/md, 4 on desktop/lg) capped at **12 articles per page** — a 4×3 grid at desktop width — with its own independent pagination (`NewsState.category_pages`, keyed per news type).
- **Per-section source filter**: a dropdown (`rx.select`) at the right edge of each section's own heading row (`justify="between"` — heading + live filtered article count on the left, dropdown on the right), listing every real publisher that contributed to that specific category, sorted by contribution count (most-articles-first, ties alphabetical), always starting with an "All" option. Picking a source (`NewsState.set_category_source`) filters that section's own articles to just that publisher and resets it to page 1 — every other section's own filter/page state is untouched, same per-category independence its pagination already had.
- **First/last pagination jumps**: each section's pagination row now has four controls — double-chevron-left (`NewsState.first_page`, jumps straight to page 1), single-chevron-left (previous page), the "Page X of Y" indicator, single-chevron-right (next page), and double-chevron-right (`NewsState.last_page`, jumps straight to the final page) — useful now that some sections run to 8–11 pages.
- **Images follow the visible pagination page**: all pagination and source-filter handlers are background events that switch the section immediately, resolve any missing images among only those 12 visible regular-news cards, persist the results, and patch the open Reflex state. This avoids waiting for every archived article to be processed before the page can show complete cards.
- Each card keeps its colored publisher badge and normalized news-type badge together on the left, places the relative publication time at the far right, and includes the title (external link) plus a short extracted-text snippet. Publisher badges remain hashed to stable colors; category badges use fixed semantic colors.
- An empty state ("No news articles yet — run app/services/news_pipeline.py...") when the table is empty or doesn't exist yet, and a skeleton grid (also 4×3 at desktop width, matching the real grid) while `NewsState.load_news` is fetching — same loading-state conventions as the rest of this app.
</details>

<details>
<summary><strong>📊 What the current page counts mean (and don't mean)</strong></summary>

As of 2026-09-30 (Telegram merged into the main sections): Cryptocurrency 3,110 (2,661 Telegram + 449 web), Artificial Intelligence 418 (261 + 157), Markets & Finance 552 (496 + 56), Technology 147 (web only; no Telegram groups are tagged Technology) — all at 12 articles/page. Because Telegram posts are far more frequent and newer, a category's first page is mostly Telegram; the source dropdown narrows a section to one publisher. These numbers will shift as the pipeline runs add new articles/posts and old ones age out of the 90-day window; they aren't a fixed target.

**Important framing, since it's easy to read a page count as "this is all the news that exists"**: this archive is not — and was never meant to be — a complete record of every article/post from every publisher/group globally. It's the output of a specifically-scoped set of ingestion pipelines: 12 curated RSS feeds' own *current* snapshot (RSS structurally can't expose history that's rolled off the feed, only today's front page), the top 100 Google News results per run across 18 topic queries, a one-time curated-outlet historical backfill, and 15 specific Telegram groups the user is a member of. A page count reflects that scope, not the total volume of real-world news/posts in a category — see `app/services/news_pipeline.py`'s own `MAX_RESULTS_PER_QUERY`/`GOOGLE_NEWS_QUERIES` constants, or `app/services/telegram_pipeline.py`'s own `TELEGRAM_GROUPS` list, if broader coverage is ever wanted.
</details>

<details>
<summary><strong>🔗 Direct links to each news category</strong></summary>

Every section has a stable `id` (`NewsState.news_sections`' own `"anchor_id"` field, slugified from the normalized news type), so `/news#cryptocurrency`, `/news#artificial-intelligence`, `/news#markets-finance`, and `/news#technology` jump directly to that category's coverage.

**A real bug found and fixed while building this**: a plain `#fragment` only auto-scrolls to content already present the moment the browser parses the URL — this page's own sections render asynchronously (`NewsState.load_news` does a real DB fetch first), so a fresh or shared link's native hash-scroll fired too early and found nothing, confirmed live. Fixed with a small script (`assets/chain_pills.js`) that polls briefly for the target section to exist, then scrolls to it — also re-runs on `hashchange` so clicking a same-page `#section` link works after the initial load too. This also surfaced (and fixed) a separate pre-existing gap: `frontend.py::news_page` wasn't loading `chain_pills.js` at all, so the header's own search/profile-dropdown click-outside-close handlers were silently missing on this page — `_placeholder_page` (used by `/narrative`, `/chains`, `/tools`, `/watchlist`) has the same gap, not fixed here since it's a different page's own template, out of scope for this pass.
</details>

<details>
<summary><strong>📨 Telegram group ingestion</strong></summary>

`app/services/telegram_pipeline.py` — a separate standalone module (different transport, different dependency: a live authenticated user session vs. stateless HTTP) that reads 17 real Telegram groups the user is a member of, each tagged with which `/news` category its posts belong to (see the group→category list below) — via [Telethon](https://docs.telethon.dev/) (the MTProto *client* library, logging in as the user's own Telegram account, not a bot).

**Why a user session instead of a bot**: the user is a member of all 17 groups but not an admin of any of them. A bot can only ever see messages posted *after* it's added as a member (no history at all), and adding a bot at all needs the group's "Add Members" permission, which some groups restrict to admins only — a real, unpredictable blocker for a non-admin member. Reading as an already-joined member via Telethon needs no group-side permission whatsoever and gets full history, not just messages from the moment of setup forward.

**One-time manual login required**: Telegram's login flow needs a verification code sent live to the account's own phone/Telegram app, which nothing automated can supply — `scripts/telegram_login.py` is a small script the user runs themselves, once, in their own terminal; it saves a local session file (`telegram_session.session`, gitignored, never committed) that the pipeline then reuses non-interactively forever after.

**Each group is tagged with which category it belongs to** — Crypto, AI, Finance, or Tech — stored as `category_or_query='Telegram <tag>'`. `NewsState._normalize_news_type` maps the `"Telegram <tag>"` label to that tag's main category via `_TELEGRAM_CATEGORY_MAP` (needed because a tag like "AI" contains none of the keywords the generic matching looks for), so a Telegram post appears in the **same** section as that category's web articles, sorted by time. **This merge is intentional (user request, 2026-09-30) — don't restore the separate sections.** Between 2026-09-29 and 2026-09-30 Telegram briefly had its own "`<Category>` Telegram News" sections; a concurrent session once reverted the merge thinking it was an accident, which is why this is spelled out here and in CLAUDE.md.

Current group→category assignments: **Cryptocurrency** — WatcherGuru, Cryptocurrency Media, Lookonchain, Bitcoin, Cointelegraph, Wu Blockchain News, Crypto | Bitcoin | Ethereum | Altcoin | News, Crypto News, Sarjana Crypto, Layergg, WhaleBot Alerts, CryptoQuant, Coin Signals, Crypto Memes (14 groups). **Markets & Finance** — Fin Watch (reassigned from Crypto per explicit request), Intraday.my (new). **Artificial Intelligence** — AI Post (new).

Each card additionally shows a blue **"Telegram News"** badge next to its real source badge (the group's own display title, e.g. "Watcher Guru", not the `@username` slug) — with Telegram mixed into the category sections, this badge is what tells a Telegram post apart from a web article. Since a Telegram message has no separate headline/body split the way an article does, the card's title is the post's own first line (truncated), and the full message text is the snippet.

**Idempotent and incremental**, same guarantee as the RSS/Google News pipeline: each post's permalink (`https://t.me/<group>/<message_id>`) is `UNIQUE` in `news_articles`, and every run after a group's first uses Telethon's own `min_id` parameter (the highest message id already stored for that group, parsed back out of its own stored URLs) to fetch only genuinely new messages — no re-walking or re-checking anything already on file. A group fetched for the first time goes back up to 30 days or 2,000 messages, whichever comes first (was 90 days / 300 messages before 2026-09-30). On `/news`, Telegram posts older than 30 days are hidden but kept in the database; web articles keep a 90-day window.

**Safety**: read-only, always — never joins a channel, sends a message, or performs any write action, which is the lowest-risk use of a personal account's session under Telegram's ToS. A 1-second pause between groups adds polite pacing on top of that. Real live first-run result: all 15 groups ingested successfully, 3,261 messages inserted, 428 skipped (media-only posts with no caption text — a photo/sticker with nothing to say has no content to show as a title, so it's dropped rather than stored empty; this app never re-hosts Telegram's own media itself).

**Known limitation**: eight high-volume groups (WatcherGuru, Bitcoin, Wu Blockchain News, Crypto News, Fin Watch, WhaleBot Alerts, Intraday.my, AI Post) were first fetched under the old 300-message cap. A few of them (notably Cryptocurrency Media, ~300 posts in ~5 days) still have less than 30 days of history stored. This doesn't self-heal: incremental runs only fetch *forward* from the highest message id already stored.
</details>

<details>
<summary><strong>⚡ Real-time listener and page auto-refresh</strong></summary>

`app/services/telegram_listener.py` is a standalone, always-on process — start it from the repo root with `python -m app.services.telegram_listener` (it isn't started automatically). It keeps one connection open to Telegram, which pushes each new post from the 17 groups as it's published; it's stored within seconds (verified: a Watcher Guru post published 17:49:35 UTC was stored at 17:49:42). Polling every minute was rejected: 17 groups every minute is ~24k requests/day from a personal account, the pattern that gets accounts rate-limited.

- **Catch-up pass**: on startup and every 30 minutes, the same process fetches each group's posts since its last stored one and retries image downloads for posts from the last 2 hours. This covers pushes Telegram occasionally doesn't deliver (one Crypto Memes post in testing) and anything posted while the listener was off.
- **Dialogs must be loaded**: Telegram only pushes a channel's new posts to a client that has loaded its chat list, so the listener calls `get_dialogs()` at startup. Without it, the listener stayed connected but received nothing.
- **One process per session file**: `telegram_session.session` is SQLite, so the scheduler no longer runs a Telegram job, and the manual one-shot `python app/services/telegram_pipeline.py` must not run while the listener is running ("database is locked").
- **Page auto-refresh**: `NewsState.watch_new_articles` checks every 60 s whether new rows exist (the table's max id moved) and reloads the list if so, so an open `/news` tab shows new posts without a reload. The full article list is kept server-side (`_all_articles`), so each refresh sends only the visible page slices to the browser.
</details>

<details>
<summary><strong>🖼️ Real photo/video images from the post itself</strong></summary>

`_download_message_image` (`telegram_pipeline.py`) downloads a real thumbnail straight from the message's own media (`thumb=-1` — the largest available thumbnail, works for both photo posts and a video's own thumbnail; plenty for a 160px card, far cheaper than a full-resolution download) into `frontend/assets/telegram_media/`, wired into ingestion for every new message. `backfill_missing_images` catches up every already-stored row that predates this feature (batched via Telethon's `get_messages`, up to 100 ids per call, grouped by group) — ran live: **2,048 of 3,836 rows got a real image**. **Per explicit decision (asked directly, given a concurrent session had just removed an equivalent fallback from the RSS/Google News side for being "misleading" — see that section above): a text-only Telegram post with no real photo/video shows no image at all, never a generic topic-matched search result (Google Images/Unsplash/etc.)** — only ever a real image the post itself actually has.

**Group profile picture instead of the generic image**: a Telegram post with no photo/video of its own shows its group's profile picture (per explicit request, applied to every Telegram post in every category, on cards and in the article reader) rather than the category fallback image. `telegram_pipeline.ensure_group_avatar` downloads each group's picture at full size (640×640; the default small version is 160×160 and blurry when stretched across a card) to `frontend/assets/telegram_media/_avatar_<username>.jpg`, during every catch-up pass, refreshing files older than 7 days. `news_state._telegram_group_avatar` maps a post's `t.me/<username>/<id>` URL to that file, and `_build_article_row` uses it as the image (and as the broken-image fallback) for Telegram rows. It's display-only, never stored in Postgres, so a group changing its picture updates all its posts within a week. If a group has no picture or the file is missing, the category fallback image still applies.

**A real architectural bug found and fixed while verifying this live**: Reflex's own asset serving copies `frontend/assets/` into a build-time snapshot (`frontend/.web/public/`) — a file the pipeline downloads *after* the app was last compiled 404s until the next restart, confirmed live with a dropped-in test file that stayed unreachable. Since the pipeline keeps downloading new images on every scheduled run (every 30 min), this would have meant images silently going stale/missing forever without a manual restart. Fixed properly by mounting a real Starlette `StaticFiles` route directly onto Reflex's backend ASGI app via `api_transformer` (Reflex's own documented extension point — mirrors the same pattern Reflex's own `app.py` already uses internally for `rx.upload`'s uploaded-files route) — serves straight from disk on every request, confirmed live that a freshly-downloaded file is reachable with zero restart needed.
</details>

<details>
<summary><strong>🔤 Literal Markdown syntax stripped from titles/snippets</strong></summary>

Telethon's `message.text` (used for title/body) re-serializes the message's real rich-text formatting entities back into literal Markdown syntax — e.g. a genuine bold run in the original Telegram post becomes the literal characters `**bold**` in the returned string. Since these cards render plain text, not Markdown, this showed up as literal asterisks/underscores/backticks/link-brackets on the page (confirmed live, e.g. "Bitcoin hits **$83,000**" rendering with the asterisks visible). Fixed for new ingestion by switching to `message.raw_text` (the message's own plain text, with formatting entities simply dropped — no syntax at all). `scripts/clean_telegram_markdown.py` is a one-time historical cleanup for rows already stored before this fix (pure Postgres read+update, no Telethon/live session involved) — ran live: **2,400 of 3,836 rows had literal Markdown syntax stripped** from their title and/or body text.
</details>

<details>
<summary><strong>📖 Internal article reader and source-body scan</strong></summary>

Every card now opens an internal `/news/[news_category]/[article_slug]` reader instead of navigating directly away from Repace. The route is human-readable (for example, `/news/cryptocurrency/bitcoin-etf-inflows-leave-institutional-demand-unclear-coinshares`) while the resolver maps it deterministically back to its permanent archive record. If multiple records in one normalized category share the same title slug, later records receive stable `-1`, `-2`, and so on suffixes; existing paths do not change as the grid's rolling 90-day window moves forward.

Its editorial layout uses a constrained reading column with the real source/category/date metadata and a responsive desktop source rail; mobile collapses this into one reading flow. Source text remains verbatim: duplicate source headlines are omitted from the body, real line breaks are preserved, short standalone source lines render as section headings, and only unusually long unstructured lines are split at sentence boundaries. This makes extraction output readable without paraphrasing, inventing copy, or collapsing an article into one giant paragraph. The rail retains the real `View original source` link and shows three actual same-category article links under **Other News Related**. Every related card uses a consistent vertical layout: a full-width 16:9 stored publisher image is flush with the card edges above a separately padded title and short extracted excerpt, with the existing category-local fallback image used for missing or broken sources. A present but inert **View More** button sits below the three cards, reserved for future expansion. The related-cards row is itself responsive: a single column on mobile, 4 columns across from tablet/iPad width (768px) up, and back to 1 column once the reader's own layout narrows the sidebar into a rail on desktop (1280px+) — so the cards never get squeezed into that narrow rail. Telegram posts use their already-stored full message text.

An article with no extractable web body stays honest: the reader displays an unavailable state and preserves its publisher link rather than fabricating text. `news_pipeline.py --backfill-missing-bodies` is a deliberate, one-time, 1-second-paced retry for only non-Telegram rows with an empty `full_body_text`; it never overwrites existing archive content and is not on the recurring scheduler, so known publisher blocks are not repeatedly hammered. The first live run retried 221 historical gaps, recovered 2 source bodies, and correctly left 219 unavailable because their source blocked download, paywalled the page, redirected endlessly, or exposed no extractable article text. In the current trailing-90-day display set, regular-source coverage is 596 with body / 216 unavailable; all 3,832 Telegram posts already have their full text.

`reflex run --env prod --single-port` retains this project’s existing direct-dynamic-route limitation: a hard fresh request to `/news/[news_category]/[article_slug]` can receive a static-export 404 before the SPA mounts. Opening an article from the `/news` card grid is client-side and verified; fixing hard-refresh/share deep links requires separate hosting/rewrite configuration rather than a reader-component change.
</details>

<details>
<summary><strong>🔗 INTRADAY.my posts: linked article body and short source name</strong></summary>

The INTRADAY.my group posts a short teaser plus a link to the article on intraday.my. For that group, `telegram_pipeline.expand_linked_article` finds the first link to exactly `intraday.my`/`www.intraday.my` (not subdomains such as `vip.intraday.my`, nor other sites), downloads the page and extracts the article text with `trafilatura`, and stores that as the post's body in place of the teaser; the post title stays the post's own first line. If the fetch fails, the original teaser is kept. The source name is overridden from the group's Telegram slogan ("INTRADAY.my - Website Pasaran Kewangan No 1 di Malaysia") to **INTRADAY.my** (`_DISPLAY_NAME_OVERRIDES`). The same override list also shortens "Sarjana Crypto - Trading & Investing Cryptocurrency 🇮🇩" to **Sarjana Crypto** (`scripts/apply_group_display_names.py` renamed the 251 existing posts). Both apply to new posts at ingestion; `scripts/expand_intraday_links.py` did the one-time backfill (renamed 306 rows; 268 posts had a link and were all expanded, 0 failures; 38 without a link were left alone). The teaser text isn't kept, since the article contains the same information. Other groups are unaffected.
</details>

<details>
<summary><strong>🔗 Clickable links in article bodies</strong></summary>

Every URL in a post's body — Telegram posts and web articles alike — is shown in the article reader as a real link with an external-link icon that opens in a new tab (long addresses wrap instead of overflowing). `news_state._link_segments` splits each body line into plain and link segments, trims trailing punctuation and unbalanced closing brackets, and `news_detail._body_segment` renders each link segment. A URL is only linked when its host has a dot and a plausible TLD (letters only, 2–12 long, not a reserved name like `.invalid`), so garbled fragments that web-article extraction sometimes produces (e.g. `https://investor. hcaheal…`) stay plain text rather than becoming dead links. The INTRADAY.my group is excluded, because its bodies are now the linked article's own text. Grid card excerpts stay plain text, since each card is itself a link and links can't be nested. Across all stored bodies, 540 posts get 695 links.
</details>

## Automatic re-ingestion

`app/scheduler/jobs.py::run_news_pipeline_sync` (RSS/Google News) runs every `settings.news_pipeline_sync_interval_hours` (0.25h/15min default; this project's own `.env` overrides it to 0.5h/30min), gated by its `SyncLog` row (`SyncType.NEWS_PIPELINE`). This only takes effect while the FastAPI backend process (`app/main.py`) is running — it calls `start_scheduler()` on startup. Telegram is not scheduled here: it runs in its own real-time listener process (see "Real-time listener and page auto-refresh" above).

**Why frequent re-runs matter specifically for the RSS feeds (and, structurally, for Telegram's own incremental fetch)**: an RSS feed only ever exposes a site's *current* "latest N" items, not an archive — a single run can never retroactively pull 90 days of RSS history that isn't in the feed anymore. Real depth for those sources only builds up by actually running the pipeline repeatedly over time; each run picks up whatever's newly published since the last one (already-seen URLs/message ids stay skipped).

## Known, accepted gaps

- **A coin's own on-page news feed (`_x_posts_section`'s neighbor on the coin-detail page, and the Home page's sliders) are unrelated static placeholders**, not backed by this real pipeline — only this dedicated `/news` page is.
- **A few busy Telegram groups first fetched under the old 300-message cap** don't have a full 30 days of history — see the Telegram ingestion section above.
- **The same story often appears from several sources** (e.g. several Telegram groups posting the same "JUST IN", or a Telegram post plus a web article), now side by side since Telegram is merged into the main sections. Hiding duplicates is planned but not built yet: the user hasn't decided which copy should stay visible.
- **The Telegram listener must be started by hand** after a restart and stops when its terminal/session ends.
- **Telegram media-only posts (a photo/sticker with no caption) are dropped, not stored** — this pipeline only stores text and a permalink, it never re-hosts Telegram's own media itself.

<details><summary>Telegram videos and multi-media grid (reader)</summary>

Posts store a `media` JSONB list (`{type, src, poster}`; NULL = unprocessed, `[]` = none). Photos and videos up to 100 MB are downloaded into the gitignored `frontend/assets/telegram_media/` (served live with Range support); larger videos show their thumbnail with a "Watch on Telegram" link. Albums are collected from neighbouring message ids. In the reader: a single video plays inline; a video plus photos shows the video in a large full-row cell with small square photo cells; photos only show a 2-column grid (odd first cell spans the row). Grid cards show a photo only if the post has one, otherwise the video's thumbnail. Existing posts are filled by `backfill_media` (part of the listener's catch-up). Disk use grows about 1 GB/day; no pruning yet.

</details>

<details><summary>AI summary in the reader</summary>

Every reader page shows an "AI Summarizations" card above the body, generated on first open from the article's title and text plus up to 6 headlines about the same story from other outlets (Google News RSS search), and cached in `news_articles.ai_summary`. Free OpenRouter models are tried in turn (nemotron, gemma-4-31b, qwen3.8-27b) because they are often overloaded. Text-only: the image is not read. The prompt forbids facts not in the provided text/headlines.

</details>

<details><summary>Source pills per section</summary>

Each section's source filter is a horizontal pill slider: All + the 10 biggest publishers of that category, filling the space to the right of the section heading, with left/right arrow buttons (same slider as the narrative filter) and ending with a royalblue pill-shaped "Other" dropdown for the rest. Selecting resets that section to page 1; sections stay independent.

</details>

<details><summary>Per-section title search and section header layout</summary>

Each section's header is heading + count on the left, the source pill slider (shortened, centred) in the middle, and a title search box on the right (below the lg breakpoint: heading + search on one row, slider full-width below with equal spacing). The search filters that section by title (case-insensitive, 300ms debounce), combines with the source filter, resets to page 1 and updates the count; other sections are independent.

</details>

<details><summary>OpenRouter usage and cost guards</summary>

OpenRouter is only called when someone opens a page: the news reader (article summary, cached forever), the coin page (AI business summary, refreshed at most every 60 days; AI description fallback, once per coin). No scheduler or list page calls it. `app/services/ai_budget.py` adds a global cap per rolling hour (`openrouter_max_calls_per_hour`, default 60) and a per-item failure cooldown (`openrouter_failure_cooldown_minutes`, default 30). In-process only.

</details>

<details><summary>Responsive header details</summary>

On desktop the source slider fills the space between the heading and the search. The title search is small on mobile (180px) and larger from tablet up including desktop (280px, 40px tall, 16px text). On mobile the category title and its article-count badge stack vertically.

</details>

<details><summary>Reader related-news layout update</summary>

The "Other News Related" cards are 3 columns at tablet width (1 on mobile and in the desktop rail), equal height, and there is no View More button. The section title search is the same large size (40px tall, 16px text, 18px icon) at every width.

</details>

<details><summary>AI routing of mixed Telegram groups, Memecoins section</summary>

Six Telegram groups (CRYPTO NEWS, Crypto News, Crypto | Bitcoin | Ethereum | Altcoin | News, Watcher Guru, Sarjana Crypto, Coin Signals) are routed per post into Cryptocurrency / Artificial Intelligence / Markets & Finance / Technology, or Excluded (stored but hidden: signals, admin chat/opinion, promos, giveaways, memes). Government/war/geopolitics goes to Markets & Finance. New posts are classified by OpenRouter when the listener stores them (one short call, hourly-capped; on failure the group's default category is kept). The 1,426 existing posts in the 30-day window were labelled once by hand (Claude Code), not by OpenRouter. WhaleBot Alerts is no longer ingested (its rows are hidden). Crypto Memes posts all go to a new "Memecoins" section with no AI filtering.

</details>

<details><summary>Sarjana Crypto: every photo post is kept</summary>

Sarjana Crypto posts with a photo are always shown, whatever their text: a photo without a caption is stored as "📷 Photo" (default category Crypto, no AI), and a photo post the AI would have excluded as chat/opinion/signal is kept in the closest category. Photo-only members of an album already covered by a captioned post are skipped. Text-only chat/opinion/signal posts from this group are still excluded; videos without text are not stored.

</details>

<details><summary>Telegram titles skip emoji-only lines</summary>

A Telegram post's title is the first line that has real text (letters or digits); decorative emoji-only header lines and sticker emoji are skipped, and the card excerpt skips them too. A post with only an emoji/sticker keeps its emoji as the title.

</details>

<details><summary>View All and per-category pages</summary>

Each `/news` section ends with its centred pagination and a "View All" button on the right. It opens `/news/<category>` (cryptocurrency, artificial-intelligence, markets-finance, technology, memecoins): the category's newest 100 articles in the same 4-column grid, under the same header as a section (title + count, source pills with "Other", title search). No pagination on that page. Filters chosen there are shared with the `/news` section of the same category.

</details>

<details><summary>Grid is 5 columns, 15 per page</summary>

News cards are laid out 5 across at desktop width (3 on tablet, 2 on phones), on the section grids and the View All page. Each section page holds 15 cards (5 x 3), and View All shows the newest 100.

</details>

<details><summary>View All pagination and nav highlight</summary>

`/news/<category>` pages through every article of the category, 100 per page, with a centred pagination row below the grid ("Showing 101–200 of 2228 articles"); changing the source pill or search returns to page 1. The category title and count are centred at the top (no back link). The header's News link stays highlighted on any `/news/...` page.

</details>

<details><summary>Category page layout and card badge fit</summary>

On `/news/<category>` the title and count are centred with extra space above the filter row, and the search box is centred below the desktop breakpoint. A long source name in a card's badge row is cut with an ellipsis so it never overlaps the time.

</details>

<details><summary>Summarize button placeholder, no Telegram badge, linked category badge</summary>

Each `/news/<category>` page has a placeholder "Summarize What Happened Today" button (sparkles icon) at the right of the "Showing … articles" line; it does nothing yet. The "Telegram News" badge is no longer shown on any card or reader page. In the article reader, the category badge links to that category's page.

</details>

<details><summary>"Summarize What Happened Today" popup</summary>

On each `/news/<category>` page the button opens a centred popup with that category's last-24-hour summary: an overview plus themed bullet sections, a model badge and the article count; it closes with the X. While it loads, the button shows a spinner and then returns to the sparkles icon. Summaries are stored per category and Kuala Lumpur day in `news_daily_summaries`. Today's (1 Oct 2026) were written by Claude Code (no OpenRouter call); from the next day, the first click of a day generates that day's summary with OpenRouter (hourly-capped) and later clicks reuse it. A category with no news in the last 24 hours says so.

</details>

<details><summary>Sections show 2 rows; News dropdown</summary>

Each `/news` section shows 10 cards per page (2 rows of 5 on desktop). The header's News link has a hover dropdown listing the five categories.

</details>


<details><summary>Offline catch-up on page load</summary>

### 🔧 Follow-up: /news catches up after being offline (2026-10-04 session)
Per explicit request: after the server (or machine) was off, reloading `/news` showed stale posts (newest was 2026-09-30, none in the last 24h). Nothing ingested while the app ran: the RSS/Google News job lives in the FastAPI scheduler and the Telegram listener is started by hand. New `frontend/frontend/news_catchup.py::ensure_running` is called from `NewsState.load_news` (first `/news` or homepage load per server process) and starts a daemon thread that immediately, then every 5 min, runs `run_news_pipeline_sync` (its own interval gate still applies) and starts `app.services.telegram_listener` as a detached subprocess if none is running (case-insensitive `pgrep`); the listener's startup catch-up fills every missed post. `watch_new_articles` then shows new rows without a reload. **Verified**: after a restart + one `/news` load the listener started and RSS/Telegram rows from the last 24h appeared; the Telegram backfill was still running when checked. **Limits**: the hourly OpenRouter cap (60) means backfilled posts beyond it keep their group's default category; the listener now outlives the Reflex server (kill it manually to stop it). Notion pending (no Notion tool this session).

</details>


<details><summary>AI coin targeting and the news_articles lock fix</summary>

### 🔧 Feature: AI-targeted "Targeted Narrative + Coin" slider with real crypto news (2026-10-04 session)
Per explicit request. The homepage section's 20 dummy cards are replaced by real Cryptocurrency-category news, each tied by AI to ONE coin and its narrative (`app/services/news_targeting_service.py`). **AI due diligence (OpenRouter free model, same helper/fallbacks as the news summary)**: a batched prompt (10 articles per call) with a curated list of 45 narratives and each one's top-10 coins by market cap (CMC tags minus noise like VC portfolios, listings, chain ecosystems; wrapped/staked/bridged/stablecoin/tokenized coins excluded outside their own category). Rules: a story about a specific coin -> that coin; an industry/macro story -> the most affected narrative and one coin from its top 10 (prompt examples: Apple Vision Pro -> RENDER, Gensler leaving -> XRP, Larry Fink on tokenization -> ONDO); broad market -> BTC; otherwise none. **Validation**: a pick is kept only if it's in that narrative's top-10 list, or if the coin exists and is really mentioned in the text; anything else (hallucinated tickers, wrong narrative) is stored as "no target". Results live on `news_articles` (`target_symbol`, `target_cmc_id`, `target_narrative`, `target_reason`, `target_model`, `targeted_at`); each article is analysed once. Runs from `frontend/news_catchup.py`'s loop (one batch per 5-minute pass, last 72h, newest first) under `ai_budget`'s cap and failure cooldown. **UI** (`components/narrative_alerts.py`): text-only cards (source, time, narrative + ticker badges, title, 3-line excerpt) linking to the reader, in the same slider as the news strip (`news-slider-*`: drag, arrows, autoplay); `NewsState.home_targeted_news`; `watch_new_articles` now also refreshes when the number of analysed articles grows. **Not yet verified with the real AI**: OpenRouter's free tier allows only **50 requests/day in total** and it was already used up (mostly by the Telegram classifier during the backfill; resets 08:00 KL). Verified instead: parsing/validation with crafted answers (RENDER/XRP/ONDO examples accepted, NONE and a fake ticker rejected), and the UI with three articles labelled by hand through the same validation (cards rendered, auto-refreshed in 46s, zero console errors), then cleared. **Also fixed, found while testing**: `/news` froze because `NewsDB` left its connection idle in a transaction for a whole pipeline run while the listener's startup `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (which takes an exclusive lock even when the column exists) queued behind it, blocking every read. The pipeline connection is now autocommit, and all `ADD COLUMN` sites (`news_pipeline`, `telegram_pipeline`, `news_summary_service`, the new service) check `information_schema` first and use a 3s lock timeout.

</details>
