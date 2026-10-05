---
paths:
  - "app/services/telegram_*"
  - "app/services/news_*"
  - "frontend/frontend/state/news_state.py"
  - "frontend/frontend/components/news_*"
  - "frontend/frontend/news_catchup.py"
---

# Telegram + news rules

- **Telegram posts are MERGED into the main `/news` category sections (Cryptocurrency, AI, Markets & Finance, Technology, Memecoins). This is intentional and user-confirmed twice. Do not restore separate "... Telegram News" sections.** Mapping is `_TELEGRAM_CATEGORY_MAP` in `news_state.py`. Before reverting something that looks like an accident, check docs or ask: it may be another session's work.
- Ingestion: `telegram_listener.py` (live push + 30-minute catch-up) stores via `telegram_pipeline.store_message`. Telegram window is 30 days on `/news`; RSS/Google News 90 days (read-time filter; the archive is never deleted).
- Groups: `TELEGRAM_GROUPS` (username, category). `AI_CLASSIFIED_GROUPS` go through `telegram_classifier` (Crypto/AI/Finance/Tech/Excluded). Excluded posts are stored as `category_or_query = 'Telegram Excluded'` and hidden. `IMAGE_ALWAYS_GROUPS` (Sarjana Crypto) keep every photo post. `crypto_memes` -> Memecoins. `whalebotalerts` is dropped.
- Titles: first line with a letter/digit (skip emoji-only lines). Bodies: `message.raw_text` (never `message.text`, which re-adds Markdown syntax). INTRADAY.my posts store the linked intraday.my article body and are not linkified.
- Images: post photo/video thumbnail, else the group's avatar (`_avatar_<username>.jpg`), else the category fallback folder. Fallbacks are display-only, never written to Postgres. Telegram media is served live by the `/telegram_media` StaticFiles mount (`api_transformer`).
- Media storage (`app/services/telegram_media_cleanup.py`, run every 12h from `news_catchup._media_maintenance_loop`): new photos/posters are saved as `.webp` (not `.jpg`) at download time. Videos are never downloaded — only the thumbnail/poster is kept, so every video post shows "poster + Watch on Telegram" (the same non-playable path an over-size video always used; there is no size cap anymore since nothing is downloaded). Posts older than 30 days (`MEDIA_RETENTION_DAYS`) have their image/poster files deleted and `image_url`/`media` cleared so the existing fallback (avatar/category image) takes over — article text (title, body) is never touched or deleted, only media. Group avatars are never pruned.
- No generic/Wikimedia/search image fallbacks for web articles (explicit decision). Publisher RSS/`og:image`/in-content image wins.
- `NewsState` loads the list once per session; edits to existing rows need a tab reload (the 60 s watcher only detects new max id).
- Dedup of cross-source duplicate stories is planned but deferred: wait for the user (see memory `project_news_dedup_plan`).
- Reader routes: `/news/<category>/<slug>` (slug collisions get `-1`, `-2`). Category page `/news/<category>` pages 100/page. Section pages are 10/page.
