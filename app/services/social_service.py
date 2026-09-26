"""On-demand, cached X (Twitter) post fetching via Apify's "Twitter (X)
Scraper — No Login or Cookies" actor (atomus/twitter-scraper, id
Y3cgyqvI46p0VMr0m), replacing the free X "Embedded Timeline" widget — its
data backend (syndication.twitter.com) rate-limits unpredictably regardless
of traffic volume, and when it does, the widget just silently renders empty
with no error (see coin_detail.py's prior _x_timeline_section for that
history).

Only ever called from a coin detail page view (see CoinState.
refresh_social_posts, a background on_load event on /coin/[symbol]) — never
from a scheduled job — since this actor bills per tweet scraped
(pay-per-event pricing), so syncing every coin's timeline proactively would
mean paying to scrape thousands of coins nobody's actually looking at.
Gated behind a Postgres cache per coin on top of that (settings.
social_cache_ttl_hours, default 4h) so even a burst of repeat visits to the
same coin's page never re-triggers the scraper more than once per coin per
window — the same cost-control spirit as MarketDataService's own sync
cadences (rule 4).
"""

import logging
from datetime import datetime, timedelta
from urllib.parse import urlparse

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.coin import Coin

logger = logging.getLogger(__name__)


def extract_x_username(twitter_url: str | None) -> str | None:
    """Pulls the handle out of a coin's stored twitter_url, e.g.
    "https://twitter.com/dogecoin" -> "dogecoin". CMC's own data
    occasionally stores a numeric profile id here instead of a real handle
    (a pre-existing CMC data-quality wrinkle, not something this fixes) —
    that still gets passed through as-is, and the scraper call below simply
    fails gracefully for it like any other invalid handle.
    """
    if not twitter_url:
        return None
    path = urlparse(twitter_url).path.strip("/")
    username = path.split("/")[0] if path else ""
    return username or None


class SocialService:
    def __init__(self, db: Session):
        self.db = db

    def get_tweets(self, coin: Coin) -> list[dict]:
        """Returns this coin's cached top-10 posts, refreshing from the
        scraper API first if the cache is empty or older than
        settings.social_cache_ttl_hours. Never raises — a scraper failure
        or timeout just falls back to whatever's already cached (or an
        empty list if this coin has never successfully synced), so a page
        view is never broken by a flaky third-party call.
        """
        username = coin.x_username or extract_x_username(coin.twitter_url)
        if not username:
            return []
        if coin.x_username != username:
            coin.x_username = username

        ttl = timedelta(hours=settings.social_cache_ttl_hours)
        is_stale = coin.last_social_update is None or datetime.utcnow() - coin.last_social_update > ttl
        if not is_stale:
            return coin.cached_tweets or []

        fresh = self._fetch_from_scraper(username)
        if fresh is None:
            # Scraper failed/timed out/not configured — keep serving the
            # last good cache (even if stale) rather than showing nothing.
            return coin.cached_tweets or []

        coin.cached_tweets = fresh
        coin.last_social_update = datetime.utcnow()
        self.db.add(coin)
        self.db.commit()
        return fresh

    def _fetch_from_scraper(self, username: str) -> list[dict] | None:
        if not settings.apify_api_token:
            logger.info("APIFY_API_TOKEN not configured — skipping X scrape for @%s", username)
            return None
        url = f"https://api.apify.com/v2/acts/{settings.apify_actor_id}/run-sync-get-dataset-items"
        try:
            response = requests.post(
                url,
                params={"token": settings.apify_api_token},
                json={
                    "searchType": "user-tweets",
                    "handles": [username],
                    "maxItems": settings.social_max_posts,
                },
                timeout=45,
            )
            response.raise_for_status()
            items = response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("X scrape failed for @%s: %s", username, exc)
            return None

        if not isinstance(items, list):
            logger.warning("X scrape for @%s returned unexpected payload shape: %r", username, type(items))
            return None

        # Confirmed live: on a genuine run-level failure (e.g. exhausting
        # this Apify account's free-tier monthly "tweet-scraped" quota),
        # this actor still returns HTTP 200 with a single item shaped like
        # {"status": "error", "error_kind": ..., "reason": "..."} instead
        # of raising — logged distinctly here (with the actor's own reason
        # text) since this is an account/billing-level problem, not a
        # per-handle one, and would otherwise just look like an ordinary
        # "no tweet records" no-op in the logs.
        error_item = next((item for item in items if item.get("status") == "error"), None)
        if error_item is not None:
            logger.warning(
                "X scrape for @%s failed at the account/run level (%s): %s",
                username,
                error_item.get("error_kind", "unknown"),
                error_item.get("reason", ""),
            )
            return None

        # One dataset item per run is a {"record_type": "profile"} summary
        # row (bio/follower counts), not a post — real posts are the
        # {"record_type": "tweet"} rows. A handle that doesn't exist at all
        # comes back as an empty list (confirmed live), not an error or a
        # placeholder row, so no separate "no results" flag to filter for
        # here.
        tweets = [item for item in items if item.get("record_type") == "tweet"]
        if not tweets:
            logger.warning("X scrape for @%s returned no tweet records", username)
            return None

        normalized = [self._normalize(item) for item in tweets[: settings.social_max_posts]]
        # A retweet/quote whose own text is just the "RT @..." stub and has
        # no media of its own still normalizes to real text+url, so this is
        # a defensive fallback for a genuinely empty/malformed row, not the
        # common case.
        normalized = [n for n in normalized if n["text"] or n["url"]]
        if not normalized:
            logger.warning("X scrape for @%s returned no usable content after normalization", username)
            return None
        return normalized

    @staticmethod
    def _normalize(item: dict) -> dict:
        # Field names confirmed live against the configured actor's own
        # "tweet" record shape (Apify Y3cgyqvI46p0VMr0m, "user-tweets"
        # mode) — not a generic guess across different Apify X-scraper
        # actors; swapping the configured actor would need re-verifying
        # this. "media" is a list of {"type", "image_url", "video_url"}
        # dicts (confirmed live) — this only ever surfaces the first
        # photo, same single-image-per-card design as before.
        text = item.get("text") or ""

        image_url = ""
        for media_item in item.get("media") or []:
            if isinstance(media_item, dict) and media_item.get("image_url"):
                image_url = media_item["image_url"]
                break

        return {
            "text": text,
            "image_url": image_url,
            "has_image": bool(image_url),
            "url": item.get("url") or "",
            "time_display": item.get("created_at") or "",
            "likes": item.get("favorite_count") or 0,
            "replies": item.get("reply_count") or 0,
            "retweets": item.get("retweet_count") or 0,
        }
