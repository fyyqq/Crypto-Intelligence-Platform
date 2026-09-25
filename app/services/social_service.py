"""On-demand, cached X (Twitter) post fetching via a third-party scraper API
(Apify), replacing the free X "Embedded Timeline" widget — its data backend
(syndication.twitter.com) rate-limits unpredictably regardless of traffic
volume, and when it does, the widget just silently renders empty with no
error (see coin_detail.py's prior _x_timeline_section for that history).

Gated behind a Postgres cache per coin (settings.social_cache_ttl_hours,
default 4h) so a burst of coin detail page visits never re-triggers the
scraper more than once per coin per window — the same cost-control spirit
as MarketDataService's own sync cadences (rule 4).
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
                json={"twitterHandles": [username], "maxItems": 10, "sort": "Latest"},
                timeout=25,
            )
            response.raise_for_status()
            items = response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("X scrape failed for @%s: %s", username, exc)
            return None

        if not isinstance(items, list):
            logger.warning("X scrape for @%s returned unexpected payload shape: %r", username, type(items))
            return None

        # Confirmed live against the real configured actor: when it fails
        # to scrape a handle (observed for several different, definitely-
        # active accounts shortly after a burst of test calls — almost
        # certainly this actor's own scraping proxy getting rate-limited/
        # blocked by X, not anything wrong with the handle or our request),
        # it still returns HTTP 200 with `maxItems` placeholder rows shaped
        # like {"noResults": true} instead of raising an error. Every other
        # field normalizes to empty/0/false for those, so without this
        # check a bad run would silently cache a page of blank cards
        # instead of correctly falling back to the "View live posts" link.
        items = [item for item in items if not item.get("noResults")]
        if not items:
            logger.warning("X scrape for @%s returned no usable results (noResults)", username)
            return None

        normalized = [self._normalize(item) for item in items[:10]]
        # Second, content-based line of defense: also confirmed live that
        # this actor can return items with no "noResults" flag at all but
        # every real field (text, url, ...) as None/missing anyway — the
        # explicit-flag check above doesn't catch that shape. Anything that
        # normalizes to no text AND no url is unusable regardless of why,
        # so it's dropped here rather than caching a blank card for it.
        normalized = [n for n in normalized if n["text"] or n["url"]]
        if not normalized:
            logger.warning("X scrape for @%s returned no usable content after normalization", username)
            return None
        return normalized

    @staticmethod
    def _normalize(item: dict) -> dict:
        # Apify's various community X-scraper actors don't all share one
        # exact response schema, and the actor behind settings.apify_actor_id
        # can be swapped by whoever configures it — this pulls the handful
        # of field-name spellings seen across the popular ones. Verified
        # live against the actual configured actor (61RPP7dywgiy0JPD0): its
        # "text"/"url"/"likeCount"/"replyCount"/"retweetCount"/"createdAt"
        # all matched the guesses below on the first try, but its "media"
        # field turned out to be a flat list of plain image-URL strings —
        # not the dict-with-a-"photos"-key shape assumed here originally,
        # which silently dropped every image. Handled below alongside the
        # dict/nested-list shapes other actors may still use.
        text = item.get("text") or item.get("full_text") or item.get("content") or ""

        media = item.get("media")
        if isinstance(media, list):
            photos = media
        elif isinstance(media, dict):
            photos = media.get("photos") or []
        else:
            photos = item.get("images") or item.get("photos") or []
        image_url = ""
        for photo in photos if isinstance(photos, list) else []:
            if isinstance(photo, str):
                image_url = photo
                break
            if isinstance(photo, dict):
                image_url = photo.get("url") or photo.get("mediaUrl") or photo.get("media_url_https") or ""
                if image_url:
                    break

        return {
            "text": text,
            "image_url": image_url,
            "has_image": bool(image_url),
            "url": item.get("url") or item.get("twitterUrl") or item.get("permanent_url") or "",
            "time_display": item.get("createdAt") or item.get("created_at") or item.get("date") or "",
            "likes": item.get("likeCount") if item.get("likeCount") is not None else item.get("favorite_count", 0),
            "replies": item.get("replyCount") if item.get("replyCount") is not None else item.get("reply_count", 0),
            "retweets": item.get("retweetCount") if item.get("retweetCount") is not None else item.get("retweet_count", 0),
        }
