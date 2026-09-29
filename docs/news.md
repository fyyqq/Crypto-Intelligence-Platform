# News

**Route:** `/news` · **Status:** Live
**Source:** `app/services/news_pipeline.py` (ingestion), `frontend/frontend/state/news_state.py`, `frontend/frontend/components/news_page.py`, `frontend/frontend/frontend.py::news_page`

A real, ingested news feed — grouped by news type (Cryptocurrency, Artificial Intelligence, Markets & Finance, and Technology), each category its own independently-paginated section. Every card still identifies its real publisher.

**Not to be confused with:** the [Home](./home.md) page's own "All News" and "Targeted Narrative + Coin" sliders (static placeholder headlines, unrelated to this page's real data) — those stay exactly as they were, untouched by this feature.

## Features

<details>
<summary><strong>📰 Zero-API-key ingestion pipeline</strong></summary>

`app/services/news_pipeline.py` — a standalone script (no imports from the rest of this repo; genuinely copy-out-and-run-anywhere), runnable manually and invoked daily by this app's scheduler when the FastAPI backend is running. Two ingestion paths, both writing into one `news_articles` table:

1. **Real-time RSS** (`feedparser`) — three hardcoded feeds: TechCrunch (Tech), Cointelegraph (Crypto), and WIRED's own AI-tagged feed (AI). The originally-requested "Artificial Intelligence News" (artificialintelligence-news.com) was swapped for WIRED — confirmed live that site now sits behind a hard captcha wall (SiteGround's `SG-Captcha`) that returns a 176-byte redirect stub to every scripted request regardless of User-Agent, so it can never yield real articles.
2. **Dynamic 90-day historical lookback** (`pygooglenews`) across three keywords (global stock market, artificial intelligence, cryptocurrency). The search window's start/end dates are computed fresh from `datetime.date.today()` on every run — never a hardcoded date string — so the same trailing 90-day window moves forward automatically whether the script runs today, next week, or next year. Capped at 25 results per query per run (Google's own top-relevance ranking) to keep one run's runtime and target-site load reasonable — a later run naturally surfaces different results since already-seen URLs are skipped.

Every article's full body text is extracted with `trafilatura` (free, local, no API key — strips nav/ads/cookie banners down to the real article text).
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

Controlled by two environment variables read once at import: `NEWS_DB_BACKEND` (`"postgres"`, the default, or `"sqlite"`) and `NEWS_DATABASE_DSN` (a libpq DSN string for Postgres, or a file path for SQLite — defaults to this project's own local dev Postgres, or `news_fallback.db`, respectively, if unset). Schema (`news_articles`: `id`, `source_type`, `source_name`, `category_or_query`, `title`, `url` UNIQUE, `published_date`, `full_body_text`) is created with `CREATE TABLE IF NOT EXISTS` on every run — no separate migration step needed, and safe to run repeatedly. `source_name` is the one column added beyond the feature's originally-specified schema — the real display outlet (e.g. "TechCrunch", or Google News's own attributed "Reuters"/"SEC.gov"/...), needed so the `/news` page can group by real publisher rather than only the coarse `source_type` ("rss"/"google_news") or the raw search query text.

Uses raw `psycopg2`/`sqlite3` directly, not this project's own SQLAlchemy models — a deliberate, genuinely standalone script per its own spec, not a service coupled to the rest of this app's ORM layer.
</details>

<details>
<summary><strong>📋 The page itself — category-grouped, paginated grid</strong></summary>

`NewsState` (Reflex) reads `news_articles` directly from the same Postgres database the pipeline writes to — via `app.core.database.SessionLocal`, the same "reach into the real Postgres app DB directly" pattern `CoinState`'s own background refreshers already use elsewhere in this app (raw SQL `SELECT`, not an ORM model, since the pipeline itself doesn't define one either).

- `NewsState` reads each article's stored `category_or_query` alongside its publisher, then normalizes it into Cryptocurrency (`Crypto`/`cryptocurrency`), Artificial Intelligence (`AI`/`artificial intelligence`), Markets & Finance (`global stock market`), or Technology (`Tech`). A publisher-based fallback covers future unclassified RSS rows without changing stored data.
- Sections appear in a fixed reader-oriented order: Cryptocurrency, Artificial Intelligence, Markets & Finance, Technology, then General News if an unclassified article ever arrives. Each section is a responsive grid (1 column on phones, 2 on tablets, 3 on desktop) capped at 6 articles per page — a 3×2 grid at desktop width — with its own independent pagination (`NewsState.category_pages`, keyed per news type).
- Each card keeps a colored publisher badge and its relative publication time on the left, adds the normalized news-type badge on the right, and includes the title (external link) plus a short extracted-text snippet. Publisher badges remain hashed to stable colors; category badges use fixed semantic colors.
- An empty state ("No news articles yet — run app/services/news_pipeline.py...") when the table is empty or doesn't exist yet, and a skeleton grid while `NewsState.load_news` is fetching — same loading-state conventions as the rest of this app.
</details>

<details>
<summary><strong>🔗 Direct links to each news category</strong></summary>

Every section has a stable `id` (`NewsState.news_sections`' own `"anchor_id"` field, slugified from the normalized news type), so `/news#cryptocurrency`, `/news#artificial-intelligence`, `/news#markets-finance`, and `/news#technology` jump directly to that category's coverage.

**A real bug found and fixed while building this**: a plain `#fragment` only auto-scrolls to content already present the moment the browser parses the URL — this page's own sections render asynchronously (`NewsState.load_news` does a real DB fetch first), so a fresh or shared link's native hash-scroll fired too early and found nothing, confirmed live. Fixed with a small script (`assets/chain_pills.js`) that polls briefly for the target section to exist, then scrolls to it — also re-runs on `hashchange` so clicking a same-page `#section` link works after the initial load too. This also surfaced (and fixed) a separate pre-existing gap: `frontend.py::news_page` wasn't loading `chain_pills.js` at all, so the header's own search/profile-dropdown click-outside-close handlers were silently missing on this page — `_placeholder_page` (used by `/narrative`, `/chains`, `/tools`, `/watchlist`) has the same gap, not fixed here since it's a different page's own template, out of scope for this pass.
</details>

## Automatic daily re-ingestion

`app/scheduler/jobs.py::run_news_pipeline_sync` runs the pipeline once every `settings.news_pipeline_sync_interval_hours` (24h by default), gated the same once-per-interval way every other scheduled job in this app is (a `SyncLog` row per run, checked before starting). This only takes effect while the FastAPI backend process (`app/main.py`) is actually running — it calls `start_scheduler()` on startup, same as this app's other scheduled jobs.

**Why daily matters specifically for the RSS feeds (TechCrunch/Cointelegraph/WIRED)**: an RSS feed only ever exposes a site's *current* "latest N" items, not an archive — a single run can never retroactively pull 90 days of RSS history that isn't in the feed anymore. Real 90-day depth for those three sources only builds up by actually running the pipeline repeatedly over time; each day's run picks up whatever's newly published since the last one (already-seen URLs stay skipped).

**Why the Google News historical path still looks sparse per outlet, even though its own 90-day window is correct**: `MAX_RESULTS_PER_QUERY = 25` across only 3 keywords caps that path at ≤75 raw results per run, spread across dozens of different real outlets — that's a deliberate, easy-to-change module constant (see `news_pipeline.py`'s own comment on it), not a bug, and hasn't been changed as of this note pending a decision on the cap/keyword-breadth tradeoff.

## Known, accepted gaps

- **A coin's own on-page news feed (`_x_posts_section`'s neighbor on the coin-detail page, and the Home page's sliders) are unrelated static placeholders**, not backed by this real pipeline — only this dedicated `/news` page is.
