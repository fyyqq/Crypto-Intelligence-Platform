"""State for the coin list page: loads the cached CoinMarketCap data and
exposes a narrative filter, backed by the SQLModel tables in frontend/models.
"""

import asyncio
from collections import Counter
from urllib.parse import urlencode

import reflex as rx
from sqlalchemy.orm import selectinload
from sqlmodel import select

from frontend.models.coin import Coin

# CMC's Basic tier has no historical-price endpoint, and an earlier attempt to
# source a real 7d line from CoinGecko only matched ~26% of coins (and risked
# mismatches). Rather than show a real chart for some coins and nothing for
# most, every coin gets a simple directional trend line instead (one for 24h,
# one for 7d): it only encodes the sign of the % change we already have, not
# a fabricated price path.
_TREND_UP = [{"v": 0}, {"v": 1}]
_TREND_DOWN = [{"v": 1}, {"v": 0}]


def _fmt_usd(value: float) -> str:
    # Always 2 decimals (e.g. $3.11), even above $1 — was rounding to a
    # whole dollar there ("$3"), which lost precision on both the homepage
    # table's Price column and the coin detail page's big price display
    # (both read this same price_display field).
    return f"${value:,.2f}"


def _fmt_compact_usd(value: float) -> str:
    """Abbreviated $ amount for Market Cap / Volume columns, e.g. $2.43M."""
    sign = "-" if value < 0 else ""
    value = abs(value)
    for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if value >= threshold:
            return f"{sign}${value / threshold:,.2f}{suffix}"
    return f"{sign}${value:,.2f}"


def _fmt_pct(value: float) -> str:
    return f"{value:+.2f}%"


def _fmt_compact_number(value: float) -> str:
    """Abbreviated plain (non-$) count for supply figures, e.g. 19.87M."""
    for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if value >= threshold:
            return f"{value / threshold:,.2f}{suffix}"
    return f"{value:,.2f}"


def _pct_color(value: float) -> str:
    return "red" if value < 0 else "green"


def _trend_line(percent_change: float) -> tuple[list[dict], str, str]:
    if percent_change > 100:
        return _TREND_UP, "gold", "trend-gold-shine"
    if percent_change < -50:
        return _TREND_DOWN, "red", "trend-red-shine"
    if percent_change < 0:
        return _TREND_DOWN, "red", ""
    return _TREND_UP, "green", ""


# Tags that are VC-portfolio / exchange-listing noise rather than a real
# narrative — filtered out when picking the one short label to show per coin.
_NOISE_PATTERNS = (
    "portfolio",
    "ecosystem",
    "listing",
    "estate",
    "reserve",
    "taxonomy",
    "commodities",
    "alt season",
    "capital",
    "labs",
    "launchpad",
    "ventures",
)


def _pick_primary_narrative(names: list[str]) -> str:
    for name in names:
        lowered = name.lower()
        if not any(pattern in lowered for pattern in _NOISE_PATTERNS):
            return name
    return names[0] if names else ""


# Maps narrative keywords to a representative lucide icon for the badge.
# Order matters (first match wins); falls back to a generic tag icon for any
# narrative name that doesn't hit one of these — new/unseen CMC tags still
# render correctly, just with the generic icon.
_NARRATIVE_ICONS: tuple[tuple[str, str], ...] = (
    ("meme", "smile"),
    ("artificial intelligence", "cpu"),
    (" ai", "cpu"),
    ("gaming", "gamepad-2"),
    ("metaverse", "gamepad-2"),
    ("stablecoin", "dollar-sign"),
    ("nft", "image"),
    ("collectible", "image"),
    ("privacy", "eye-off"),
    ("exchange", "arrow-left-right"),
    ("storage", "database"),
    ("oracle", "radio"),
    ("payment", "credit-card"),
    ("defi", "landmark"),
    ("layer", "layers"),
)


def _narrative_icon(name: str) -> str:
    lowered = f" {name.lower()} "
    for pattern, icon in _NARRATIVE_ICONS:
        if pattern in lowered:
            return icon
    return "tag"


def _build_row(coin: Coin) -> dict:
    """Builds one table row dict from a Coin (with categories/contracts
    eager-loaded). Shared by load_coins (full load) and the view-driven
    live sync (refreshes just the coins on whichever page is on screen).
    """
    names = sorted(category.name for category in coin.categories)
    trend_24h_data, trend_24h_color, trend_24h_shine = _trend_line(coin.percent_change_24h or 0.0)
    trend_7d_data, trend_7d_color, trend_7d_shine = _trend_line(coin.percent_change_7d or 0.0)
    primary_narrative = _pick_primary_narrative(names)

    # A coin with no contract rows is single-chain — it IS its own chain.
    # Otherwise the row already flagged as primary (see
    # MarketDataService._upsert_contracts) is the main chain; everything
    # else feeds the "other chains" dropdown.
    chains = sorted(coin.contracts, key=lambda c: c.sort_order)
    primary_chain = next((c for c in chains if c.is_primary), None)
    main_chain = primary_chain.platform_name if primary_chain else coin.name
    other_chains = [c.platform_name for c in chains if c is not primary_chain]

    # Native coins (BTC, ETH, SOL...) have no contract rows at all — only
    # tokens deployed on top of another chain have a real address to show.
    contract_address = (primary_chain.contract_address if primary_chain else None) or ""
    # CMC's own /v2/info data occasionally reports a placeholder like "0"
    # for a wrapped/bridged listing that hasn't been assigned a real
    # address yet (confirmed live on TAO's Solana-Ecosystem entry) — too
    # short to be a genuine contract address (real ones are 26+ chars,
    # EVM 0x... or Solana base58), so treated as "no contract" rather than
    # displaying/copying garbage.
    if len(contract_address) < 20:
        contract_address = ""
    contract_address_display = (
        f"{contract_address[:6]}...{contract_address[-4:]}" if len(contract_address) > 14 else contract_address
    )

    # Every OTHER chain this coin is genuinely deployed on with a real
    # contract address (same >=20-char validity filter as the primary one
    # above) — feeds the Contract row's "+N chains" dropdown so a coin
    # bridged/wrapped across several chains can show all of them, not just
    # whichever one happened to be flagged primary.
    other_chain_contracts = []
    for c in chains:
        if c is primary_chain or not c.contract_address or len(c.contract_address) < 20:
            continue
        addr = c.contract_address
        other_chain_contracts.append(
            {
                "platform_name": c.platform_name,
                "contract_address": addr,
                "contract_address_display": f"{addr[:6]}...{addr[-4:]}" if len(addr) > 14 else addr,
            }
        )

    # Ordered by the same priority _links_section always rendered them in —
    # only the platforms this coin actually declared. First 3 show inline,
    # the rest (if any) collapse into a dropdown, same pattern as chains.
    social_candidates = [
        ("twitter", coin.twitter_url),
        ("github", coin.source_code_url),
        ("telegram", coin.telegram_url),
        ("reddit", coin.reddit_url),
        ("facebook", coin.facebook_url),
    ]
    social_links = [{"platform": p, "url": u} for p, u in social_candidates if u]

    vol_mkt_cap_pct = (
        coin.volume_24h_usd / coin.market_cap_usd * 100
        if coin.volume_24h_usd and coin.market_cap_usd
        else None
    )

    return {
        "cmc_id": coin.cmc_id,
        "name": coin.name,
        "symbol": coin.symbol,
        "icon_url": f"https://s2.coinmarketcap.com/static/img/coins/64x64/{coin.cmc_id}.png",
        # CMC's own rank, real-time synced on every listings/quotes call —
        # used on the coin detail page's rank badge (its "rank" key above is
        # a market-cap-position computed fresh only in filtered_coins, which
        # selected_coin bypasses by reading straight out of all_coins).
        "cmc_rank": coin.cmc_rank or 0,
        "market_cap_usd": coin.market_cap_usd or 0.0,
        "price_raw": coin.price_usd or 0.0,
        "volume_raw": coin.volume_24h_usd or 0.0,
        "pct_1h_raw": coin.percent_change_1h or 0.0,
        "pct_24h_raw": coin.percent_change_24h or 0.0,
        "pct_7d_raw": coin.percent_change_7d or 0.0,
        "price_display": _fmt_usd(coin.price_usd or 0.0),
        "market_cap_display": _fmt_compact_usd(coin.market_cap_usd or 0.0),
        "volume_display": _fmt_compact_usd(coin.volume_24h_usd or 0.0),
        "change_1h_display": _fmt_pct(coin.percent_change_1h or 0.0),
        "change_1h_color": _pct_color(coin.percent_change_1h or 0.0),
        "change_24h_display": _fmt_pct(coin.percent_change_24h or 0.0),
        "change_24h_color": _pct_color(coin.percent_change_24h or 0.0),
        "change_7d_display": _fmt_pct(coin.percent_change_7d or 0.0),
        "change_7d_color": _pct_color(coin.percent_change_7d or 0.0),
        "narratives": ", ".join(names),
        "narrative_list": names,
        "primary_narrative": primary_narrative,
        "primary_narrative_icon": _narrative_icon(primary_narrative),
        "main_chain": main_chain,
        "other_chains_display": "\n".join(other_chains),
        "has_other_chains": len(other_chains) > 0,
        "platform_list": [main_chain, *other_chains],
        "contract_address": contract_address,
        "contract_address_display": contract_address_display,
        "has_contract": bool(contract_address),
        "other_chain_contracts": other_chain_contracts,
        "has_other_chain_contracts": bool(other_chain_contracts),
        "social_links_primary": social_links[:3],
        "social_links_extra": social_links[3:],
        "has_extra_socials": len(social_links) > 3,
        # Real, already-fetched data (see MarketDataService._upsert_coins/
        # _upsert_quotes) that just wasn't persisted before now. Liq/Mkt Cap
        # and Holders still have no equivalent field on CMC's Basic tier
        # (Liquidity Score is a paid-tier metric; holder counts need a
        # separate blockchain-explorer API), so those two stay "—".
        "vol_mkt_cap_display": f"{vol_mkt_cap_pct:.2f}%" if vol_mkt_cap_pct is not None else "—",
        "fdv_display": (
            _fmt_compact_usd(coin.fully_diluted_market_cap)
            if coin.fully_diluted_market_cap
            else "—"
        ),
        "circulating_supply_display": (
            f"{_fmt_compact_number(coin.circulating_supply)} {coin.symbol}"
            if coin.circulating_supply
            else "—"
        ),
        "total_supply_display": (
            f"{_fmt_compact_number(coin.total_supply)} {coin.symbol}" if coin.total_supply else "—"
        ),
        "max_supply_display": (
            f"{_fmt_compact_number(coin.max_supply)} {coin.symbol}" if coin.max_supply else "—"
        ),
        "website_url": coin.website_url or "",
        "whitepaper_url": coin.whitepaper_url or "",
        "twitter_url": coin.twitter_url or "",
        "telegram_url": coin.telegram_url or "",
        "source_code_url": coin.source_code_url or "",
        "explorer_url": coin.explorer_url or "",
        "reddit_url": coin.reddit_url or "",
        "facebook_url": coin.facebook_url or "",
        "has_website": bool(coin.website_url),
        "has_whitepaper": bool(coin.whitepaper_url),
        "has_twitter": bool(coin.twitter_url),
        "has_telegram": bool(coin.telegram_url),
        "has_source_code": bool(coin.source_code_url),
        "has_explorer": bool(coin.explorer_url),
        "has_reddit": bool(coin.reddit_url),
        "has_facebook": bool(coin.facebook_url),
        "description": coin.description or "",
        "has_description": bool(coin.description),
        # Cached X posts (see app/services/social_service.py) — already
        # normalized {text, image_url, has_image, url, time_display, likes,
        # replies, retweets} dicts, refreshed on-demand via
        # CoinState.refresh_social_posts rather than by this row build.
        "cached_tweets": coin.cached_tweets or [],
        "has_cached_tweets": bool(coin.cached_tweets),
        "trend_24h_data": trend_24h_data,
        "trend_24h_color": trend_24h_color,
        "trend_24h_shine": trend_24h_shine,
        "trend_7d_data": trend_7d_data,
        "trend_7d_color": trend_7d_color,
        "trend_7d_shine": trend_7d_shine,
    }


def _sync_and_rebuild_rows(cmc_ids: list[int]) -> dict[int, dict]:
    """Blocking work for the view-driven live sync: refreshes the given
    coins' quotes in Postgres (cross-package call into the FastAPI
    backend's own service, same pattern as reflex_cache_service.py's
    Postgres->Reflex mirror), mirrors just those rows into the Reflex
    SQLite cache, and returns freshly-built row dicts keyed by cmc_id.
    Runs in a thread (see CoinState.sync_visible_page) since it's all
    synchronous network/DB calls.
    """
    import sys
    from pathlib import Path

    from sqlalchemy import select as sa_select

    # Reflex's own process runs with only frontend/ on sys.path — the
    # project root (parent of both app/ and frontend/) needs adding before
    # `app.*` can be imported, same cross-package pattern as
    # reflex_cache_service.py uses in the other direction.
    _root = str(Path(__file__).resolve().parent.parent.parent.parent)
    if _root not in sys.path:
        sys.path.insert(0, _root)

    from app.core.database import SessionLocal as OldSessionLocal
    from app.models.coin import Coin as OldCoin
    from app.models.sync_log import SyncStatus
    from app.services.market_data_service import MarketDataService

    old_db = OldSessionLocal()
    try:
        sync_log = MarketDataService(old_db).sync_ids(cmc_ids)
        if sync_log.status != SyncStatus.SUCCESS:
            # Transient CMC/network hiccup — skip this cycle rather than
            # mirroring stale Postgres data into Reflex's cache; the next
            # tick (60s, or the next page/filter change) tries again.
            return {}
        fresh_by_id = {
            c.cmc_id: c
            for c in old_db.scalars(sa_select(OldCoin).where(OldCoin.cmc_id.in_(cmc_ids))).all()
        }
    finally:
        old_db.close()

    with rx.session() as session:
        rows = session.exec(select(Coin).where(Coin.cmc_id.in_(cmc_ids))).all()
        for row in rows:
            fresh = fresh_by_id.get(row.cmc_id)
            if fresh is None:
                continue
            row.cmc_rank = fresh.cmc_rank
            row.price_usd = float(fresh.price_usd) if fresh.price_usd is not None else None
            row.market_cap_usd = float(fresh.market_cap_usd) if fresh.market_cap_usd is not None else None
            row.volume_24h_usd = float(fresh.volume_24h_usd) if fresh.volume_24h_usd is not None else None
            row.percent_change_1h = (
                float(fresh.percent_change_1h) if fresh.percent_change_1h is not None else None
            )
            row.percent_change_24h = (
                float(fresh.percent_change_24h) if fresh.percent_change_24h is not None else None
            )
            row.percent_change_7d = (
                float(fresh.percent_change_7d) if fresh.percent_change_7d is not None else None
            )
            row.last_synced_at = fresh.last_synced_at
            session.add(row)
        session.commit()

        updated_coins = session.exec(
            select(Coin)
            .where(Coin.cmc_id.in_(cmc_ids))
            .options(selectinload(Coin.categories), selectinload(Coin.contracts))
        ).all()
        return {coin.cmc_id: _build_row(coin) for coin in updated_coins}


def _fetch_social_posts(symbol: str) -> tuple[int, list[dict]] | None:
    """Blocking work for the on-demand X-post refresh (see CoinState.
    refresh_social_posts): finds the coin by ticker directly in Postgres —
    not via self.selected_coin, so this doesn't race load_coins for the same
    on_load — using the same highest-market-cap tie-break CoinState.
    selected_coin uses (tickers aren't unique on CMC), then delegates to
    SocialService (app/services/social_service.py), which enforces its own
    4h cache window: most calls here just replay the already-cached tweets
    rather than re-hitting the scraper API. Mirrors the refreshed fields
    into the Reflex SQLite cache directly (same cross-package pattern as
    _sync_and_rebuild_rows above) so they survive independently of the next
    24h/1h full mirror rebuild. Returns None if no coin matches this ticker.
    """
    import sys
    from pathlib import Path

    from sqlalchemy import select as sa_select

    _root = str(Path(__file__).resolve().parent.parent.parent.parent)
    if _root not in sys.path:
        sys.path.insert(0, _root)

    from app.core.database import SessionLocal as OldSessionLocal
    from app.models.coin import Coin as OldCoin
    from app.services.social_service import SocialService

    old_db = OldSessionLocal()
    try:
        matches = old_db.scalars(sa_select(OldCoin).where(OldCoin.symbol.ilike(symbol))).all()
        if not matches:
            return None
        coin = max(matches, key=lambda c: c.market_cap_usd or 0.0)
        tweets = SocialService(old_db).get_tweets(coin)
        cmc_id = coin.cmc_id
        x_username = coin.x_username
        last_social_update = coin.last_social_update
    finally:
        old_db.close()

    with rx.session() as session:
        row = session.exec(select(Coin).where(Coin.cmc_id == cmc_id)).first()
        if row is not None:
            row.x_username = x_username
            row.cached_tweets = tweets
            row.last_social_update = last_social_update
            session.add(row)
            session.commit()

    return cmc_id, tweets


class CoinState(rx.State):
    all_coins: list[dict] = []
    categories: list[str] = []
    selected_category: str = "All narratives"
    # Drives just the pill's active/blue highlight. Kept separate from
    # selected_category (which drives the actual re-filter/re-sort of up to
    # 8154 coins) so the clicked pill highlights instantly instead of
    # waiting on that heavier computation to finish.
    active_category: str = "All narratives"
    chains: list[str] = []
    selected_chain: str = "All chains"
    active_chain: str = "All chains"
    is_loading: bool = True
    is_filtering: bool = False
    page: int = 1
    # Drives just the pagination number's active/blue highlight, same
    # instant-highlight-then-load pattern as active_category above — updated
    # before the sleep so the clicked page number turns blue immediately
    # instead of waiting on the skeleton's artificial delay.
    active_page: int = 1
    page_size: int = 100

    # Search-by-name/ticker across every coin (not just the current page) —
    # search_open toggles the magnifying-glass icon into the input field.
    search_open: bool = False
    search_query: str = ""

    # In-page sort only: reorders the current page's rows, never re-ranks
    # across the full coin list. sort_key is one of the raw numeric fields
    # in each row dict (e.g. "pct_1h_raw"), or "" for the default (market-cap)
    # order. sort_direction cycles "desc" (1st click, biggest -> smallest, top
    # arrow active) -> "asc" (2nd click, smallest -> biggest, bottom arrow
    # active) -> neutral (3rd click, both "", back to default order).
    # Changing page also resets both, per spec.
    sort_key: str = ""
    sort_direction: str = ""

    # Backend-only (not sent to the client): guards live_sync_loop against
    # starting twice for the same session (e.g. on_load firing again).
    _is_live_syncing: bool = False
    # Same guard as _is_live_syncing above, for detail_sync_loop.
    _is_detail_syncing: bool = False

    # Drives the coin detail page's centered "Copied to clipboard" popup —
    # set true right when the Contract pill is clicked (see coin_detail.py's
    # on_click list, chained after the actual rx.set_clipboard), then flips
    # back after 3s below.
    contract_copied: bool = False

    @rx.event
    def load_coins(self):
        self.is_loading = True
        with rx.session() as session:
            coins = session.exec(
                select(Coin)
                .options(selectinload(Coin.categories), selectinload(Coin.contracts))
                .order_by(Coin.cmc_rank)
            ).all()

            rows: list[dict] = []
            narrative_counts: Counter[str] = Counter()
            chain_counts: Counter[str] = Counter()
            for coin in coins:
                narrative_counts.update(category.name for category in coin.categories)
                row = _build_row(coin)
                chain_counts.update([row["main_chain"]])
                rows.append(row)

        self.all_coins = rows
        # Top 20 by number of coins carrying that tag — out of ~600 dynamic
        # CMC categories, this keeps the filter pill bar to the narratives
        # that actually matter for most coins shown, not an alphabetical cut.
        top_narratives = [name for name, _ in narrative_counts.most_common(20)]
        self.categories = ["All narratives", *top_narratives]
        # Top 20 chains by number of coins whose primary/native chain it is
        # — same "most common" approach as narratives, dynamically computed
        # each sync rather than a fixed chain list.
        top_chains = [name for name, _ in chain_counts.most_common(20)]
        self.chains = ["All chains", *top_chains]
        self.is_loading = False

    @rx.event
    async def set_category(self, value: str):
        # active_category has no dependent computed vars, so this first
        # flush (pill turns blue + skeleton shows) is instant. The sleep
        # below is what keeps the skeleton visible — re-filtering an
        # in-memory list is itself instant, so without it the second flush
        # (updating selected_category) would follow within a millisecond
        # and the skeleton would never actually be perceptible.
        self.active_category = value
        self.active_page = 1
        self.is_filtering = True
        yield
        await asyncio.sleep(0.25)
        self.selected_category = value
        self.page = 1
        self.sort_key = ""
        self.sort_direction = ""
        self.is_filtering = False
        yield CoinState.sync_visible_page

    @rx.event
    async def set_chain(self, value: str):
        # Same instant-highlight-then-refilter pattern as set_category. The
        # two filters combine with AND (see filtered_coins) — narrative +
        # chain together, e.g. "Memes" + "BNB Smart Chain (BEP20)".
        self.active_chain = value
        self.active_page = 1
        self.is_filtering = True
        yield
        await asyncio.sleep(0.25)
        self.selected_chain = value
        self.page = 1
        self.sort_key = ""
        self.sort_direction = ""
        self.is_filtering = False
        yield CoinState.sync_visible_page

    @rx.event
    async def toggle_search(self):
        self.search_open = not self.search_open
        if self.search_open:
            # The desktop input stays permanently mounted (only a CSS class
            # toggles its width/opacity — see coin_table.py's _coin_search
            # docstring), so a static auto_focus prop never refires on
            # reopen. rx.call_script explicitly focuses it by id instead.
            yield rx.call_script("document.getElementById('coin-search-input-field')?.focus()")
            return
        if self.search_query:
            self.active_page = 1
            self.is_filtering = True
            yield
            await asyncio.sleep(0.25)
            self.search_query = ""
            self.page = 1
            self.is_filtering = False
            yield CoinState.sync_visible_page

    @rx.event
    async def set_search_query(self, value: str):
        # search_query updates immediately (keeps the input's own value in
        # sync). The skeleton — not the new, already-filtered rows — is
        # what actually renders until the flush below. Re-filtering an
        # in-memory list is itself instant, so without the artificial
        # delay the skeleton would flash for under a millisecond and never
        # actually be visible; the sleep is what makes the loading state
        # perceptible at all.
        self.search_query = value
        self.active_page = 1
        self.is_filtering = True
        yield
        await asyncio.sleep(0.25)
        self.page = 1
        self.sort_key = ""
        self.sort_direction = ""
        self.is_filtering = False
        yield CoinState.sync_visible_page

    @rx.event
    async def next_page(self):
        if self.page < self.total_pages:
            self.active_page = self.page + 1
            self.is_filtering = True
            yield
            await asyncio.sleep(0.25)
            self.page += 1
            self.sort_key = ""
            self.sort_direction = ""
            self.is_filtering = False
            yield CoinState.sync_visible_page

    @rx.event
    async def prev_page(self):
        if self.page > 1:
            self.active_page = self.page - 1
            self.is_filtering = True
            yield
            await asyncio.sleep(0.25)
            self.page -= 1
            self.sort_key = ""
            self.sort_direction = ""
            self.is_filtering = False
            yield CoinState.sync_visible_page

    @rx.event
    async def go_to_page(self, page_str: str):
        page = int(page_str)
        if 1 <= page <= self.total_pages:
            self.active_page = page
            self.is_filtering = True
            yield
            await asyncio.sleep(0.25)
            self.page = page
            self.sort_key = ""
            self.sort_direction = ""
            self.is_filtering = False
            yield CoinState.sync_visible_page

    @rx.event
    async def set_page_size(self, value: str):
        self.active_page = 1
        self.is_filtering = True
        yield
        await asyncio.sleep(0.25)
        self.page_size = int(value)
        self.page = 1
        self.sort_key = ""
        self.sort_direction = ""
        self.is_filtering = False
        yield CoinState.sync_visible_page

    @rx.event(background=True)
    async def sync_visible_page(self):
        """One-shot view-driven refresh: re-fetches quotes for just the
        coins on whichever page/filter is on screen right now (called
        immediately after pagination/filter changes; live_sync_loop below
        covers the same page while it stays open, every 60s).
        """
        async with self:
            cmc_ids = [row["cmc_id"] for row in self.sorted_paged_coins]
        if not cmc_ids:
            return
        updated_rows = await asyncio.to_thread(_sync_and_rebuild_rows, cmc_ids)
        async with self:
            self._apply_updates(updated_rows)

    @rx.event(background=True)
    async def live_sync_loop(self):
        """Keeps the global top 100 coins (by market cap, regardless of
        whatever page/filter is on screen) fresh every 60s for as long as
        that browser tab stays open — started once via on_load — plus
        whichever page/filter the session is actually looking at right now,
        if that's a different set (e.g. a user parked on page 3). Top 100
        coins are the ones every session cares about most (Bitcoin, Ethereum,
        etc.), so those stay live even while someone's browsing deeper pages,
        not just whatever happens to be on screen. Rule 4 (API Optimization &
        Cost Control) still holds for the full ~8,000-coin universe (24h
        cadence, sync_hot_listings' top-500/1h cadence); this only ever
        touches <=200 coins, one lightweight quotes/latest call at a time.
        """
        async with self:
            if self._is_live_syncing:
                return
            self._is_live_syncing = True

        from frontend.frontend import app as reflex_app

        try:
            while True:
                # Sync runs before the connection check (not after) — right
                # after on_load fires, the websocket handshake that
                # registers this client_token in token_to_sid may not have
                # completed yet, and checking first would break out before
                # ever syncing anything.
                async with self:
                    top_100_ids = [
                        row["cmc_id"]
                        for row in sorted(
                            self.all_coins, key=lambda r: r["market_cap_usd"], reverse=True
                        )[:100]
                    ]
                    visible_ids = [row["cmc_id"] for row in self.sorted_paged_coins]
                    # dict.fromkeys dedupes while preserving order — avoids a
                    # duplicate CMC API lookup for coins in both sets (the
                    # common case: page 1 IS the top 100).
                    cmc_ids = list(dict.fromkeys([*top_100_ids, *visible_ids]))
                if cmc_ids:
                    updated_rows = await asyncio.to_thread(_sync_and_rebuild_rows, cmc_ids)
                    async with self:
                        self._apply_updates(updated_rows)
                await asyncio.sleep(60)
                if self.router.session.client_token not in reflex_app.event_namespace.token_to_sid:
                    break
        finally:
            async with self:
                self._is_live_syncing = False

    def _apply_updates(self, updated_rows: dict[int, dict]) -> None:
        if not updated_rows:
            return
        self.all_coins = [updated_rows.get(row["cmc_id"], row) for row in self.all_coins]

    @rx.event
    def go_to_coin(self, symbol: str):
        return rx.redirect(f"/coin/{symbol.lower()}")

    @rx.event(background=True)
    async def show_copied_toast(self):
        """Shows the centered "Copied to clipboard" popup for exactly 3s.
        Chained after rx.set_clipboard on the Contract pill's on_click (see
        coin_detail.py) — that copy itself is a client-only special event,
        so this is what actually confirms it happened.
        """
        async with self:
            self.contract_copied = True
        await asyncio.sleep(3)
        async with self:
            self.contract_copied = False

    @rx.var(cache=True)
    def selected_coin(self) -> dict:
        """Looks up the coin for the current /coin/[symbol] route straight
        out of the already-cached all_coins list — no extra DB query needed
        since load_coins (shared on_load with the homepage) already loaded
        the full universe.

        `self.symbol` is not declared anywhere on this class — Reflex
        auto-injects it as a computed var on the root State once
        app.add_page registers the "/coin/[symbol]" dynamic route (see
        BaseState.setup_dynamic_args), the same mechanism the framework
        docs describe for a `[pid]`-style route.

        Tickers aren't unique on CMC — plenty of low-cap/scam tokens reuse a
        popular symbol — so ties are broken by market cap. Someone visiting
        "/coin/eth" almost always means Ethereum, not an obscure same-ticker
        micro-cap.
        """
        symbol = self.symbol.strip().lower()
        if not symbol:
            return {}
        matches = [row for row in self.all_coins if row["symbol"].lower() == symbol]
        if not matches:
            return {}
        return max(matches, key=lambda r: r["market_cap_usd"])

    @rx.var(cache=True)
    def selected_coin_found(self) -> bool:
        return bool(self.selected_coin)

    @rx.event(background=True)
    async def detail_sync_loop(self):
        """Keeps just the single coin shown on this /coin/[symbol] page
        fresh every 60s for as long as the tab stays open — same sync
        primitive as live_sync_loop (rule 4: cheap, targeted quotes/latest
        calls only), just scoped to the one coin being viewed instead of the
        homepage's top-100/visible-page set.
        """
        async with self:
            if self._is_detail_syncing:
                return
            self._is_detail_syncing = True

        from frontend.frontend import app as reflex_app

        try:
            while True:
                async with self:
                    cmc_id = self.selected_coin.get("cmc_id")
                if cmc_id:
                    updated_rows = await asyncio.to_thread(_sync_and_rebuild_rows, [cmc_id])
                    async with self:
                        self._apply_updates(updated_rows)
                await asyncio.sleep(60)
                async with self:
                    still_connected = (
                        self.router.session.client_token in reflex_app.event_namespace.token_to_sid
                    )
                if not still_connected:
                    break
        finally:
            async with self:
                self._is_detail_syncing = False

    @rx.event(background=True)
    async def refresh_social_posts(self):
        """One-shot, on-demand refresh of this coin's cached X posts — fired
        once per page view (see frontend.py's /coin/[symbol] on_load), not on
        a loop like detail_sync_loop above: SocialService itself enforces a
        4h cache window (settings.social_cache_ttl_hours), so most page
        views just replay the already-cached tweets rather than re-hitting
        the scraper API.

        Looks the coin up by ticker directly in Postgres (see
        _fetch_social_posts) rather than through self.selected_coin, so it
        never races load_coins for the same on_load — if this finishes
        before load_coins populates all_coins, the fresh tweets are still
        safely on disk in the Reflex SQLite mirror by the time load_coins
        (and _build_row) actually reads it.
        """
        symbol = self.symbol.strip()
        if not symbol:
            return
        result = await asyncio.to_thread(_fetch_social_posts, symbol)
        if result is None:
            return
        cmc_id, tweets = result
        async with self:
            self.all_coins = [
                {**row, "cached_tweets": tweets, "has_cached_tweets": bool(tweets)}
                if row["cmc_id"] == cmc_id
                else row
                for row in self.all_coins
            ]

    def _tradingview_iframe_src(self, theme: str) -> str:
        """Public, no-API-key TradingView "widgetembed" iframe URL. CMC's
        Basic tier has no historical OHLCV endpoint (see the _TREND_UP/
        _TREND_DOWN note above), so this is the only way to show a genuinely
        real, live-updating candlestick chart without a paid CMC plan or a
        custom price-history pipeline.

        No hardcoded exchange prefix (previously "BINANCE:{symbol}USDT") —
        confirmed live that this was cutting price history short for coins
        Binance listed later than other venues (e.g. /coin/tao only showed
        roughly half its real listing history on BINANCE:TAOUSDT). A bare
        "{symbol}USDT" lets TradingView's own symbol search resolve to
        whichever venue it considers primary, which is often — but not
        guaranteed to be — the one with the longest history; there's no
        free API that exposes "earliest listing across every CEX/DEX" to
        pick deterministically. allow_symbol_change=1 is the honest
        fallback: it keeps TradingView's own exchange switcher available
        so a viewer can manually pick a different venue if this default
        still doesn't have full history.

        Split into light/dark variants (see tradingview_iframe_src_light/
        _dark below) rather than one var, since the app's color mode is a
        client-side (next-themes) preference this server-cached var can't
        see — the component picks between the two via rx.color_mode_cond,
        which is a real frontend-reactive Var, not a server computation.

        interval="W" + range="ALL" (rather than the previous interval="60",
        no range) so the chart opens already zoomed out to a coin's entire
        listing history by default — matching CMC's own coin page, which
        opens on a weekly-candle view spanning listing low to prior ATH.
        withdateranges=1 still shows the 1h/4h/24h/1W/1M row so a viewer can
        zoom into a shorter window afterward; this only changes what loads
        first.

        backgroundColor/gridColor force a solid plot pane with no visible
        grid lines (grid color matches the background exactly, so lines
        blend in) — these are real top-level options on TradingView's free
        embeddable widget. (The nested "overrides" param used by their
        paid/self-hosted Charting Library, e.g. "paneProperties.background",
        was tried first and confirmed live to have zero effect here — this
        free widget strips that key entirely, so it silently does nothing
        rather than erroring. backgroundColor/gridColor are the ones this
        widget tier actually reads.) Follows `theme` now (black in dark
        mode, white in light mode) rather than a fixed black regardless of
        theme — matches the rest of the page's own light/dark switching.
        """
        symbol = (self.selected_coin.get("symbol") or "BTC").upper()
        pane_color = "#000000" if theme == "dark" else "#ffffff"
        params = {
            "symbol": f"{symbol}USDT",
            "interval": "W",
            "range": "ALL",
            "theme": theme,
            "style": "1",
            "locale": "en",
            "toolbarbg": "131722" if theme == "dark" else "f1f3f6",
            "backgroundColor": pane_color,
            "gridColor": pane_color,
            # Underscored key is the one this widget actually reads — the
            # earlier "hidesidetoolbar" (no underscore) was silently
            # ignored, leaving the drawing-tools sidebar hidden (its
            # default) regardless of its "0" value. Confirmed live that
            # this one shows the left toolbar while the black background/
            # grid above stay intact.
            "hide_side_toolbar": "0",
            "saveimage": "0",
            "withdateranges": "1",
            "studies": "[]",
            "hideideas": "1",
            "allow_symbol_change": "1",
        }
        return f"https://www.tradingview.com/widgetembed/?{urlencode(params)}"

    @rx.var(cache=True)
    def tradingview_iframe_src_light(self) -> str:
        return self._tradingview_iframe_src("light")

    @rx.var(cache=True)
    def tradingview_iframe_src_dark(self) -> str:
        return self._tradingview_iframe_src("dark")

    @rx.event
    def set_sort(self, key: str):
        if self.sort_key != key:
            self.sort_key = key
            self.sort_direction = "desc"
        elif self.sort_direction == "desc":
            self.sort_direction = "asc"
        else:
            # Third click on the same column: back to neutral/default order.
            self.sort_key = ""
            self.sort_direction = ""

    @rx.var(cache=True)
    def filtered_coins(self) -> list[dict]:
        rows = self.all_coins
        if self.selected_category != "All narratives":
            rows = [r for r in rows if self.selected_category in r["narratives"]]
        # AND'd with the narrative filter — e.g. "Memes" + "BNB Smart Chain
        # (BEP20)" narrows to memecoins whose primary chain is BNB Smart Chain.
        if self.selected_chain != "All chains":
            rows = [r for r in rows if r["main_chain"] == self.selected_chain]
        # Search runs against every coin in all_coins (not just the current
        # page) by name/ticker only — finds a coin regardless of which page
        # it would otherwise land on.
        if self.search_query:
            query = self.search_query.strip().lower()
            # A search is a lookup for one specific, known coin, so its rank
            # should be the coin's real global position by market cap across
            # every coin (e.g. XRP is #5) — not its position within the
            # arbitrarily narrowed search-result list, which previously
            # showed "1" for a single match regardless of that coin's actual
            # standing.
            global_rank_by_id = {
                row["cmc_id"]: i
                for i, row in enumerate(
                    sorted(self.all_coins, key=lambda r: r["market_cap_usd"], reverse=True),
                    start=1,
                )
            }
            rows = [
                {**r, "rank": global_rank_by_id[r["cmc_id"]]}
                for r in rows
                if query in r["name"].lower() or query in r["symbol"].lower()
            ]
            return sorted(rows, key=lambda r: r["market_cap_usd"], reverse=True)
        rows = sorted(rows, key=lambda r: r["market_cap_usd"], reverse=True)
        # Rank reflects position by market cap in the current view (1..N),
        # not CMC's own cmc_rank field, which has gaps/different methodology
        # (e.g. staked derivatives) that don't match a strict market-cap order.
        return [{**row, "rank": i} for i, row in enumerate(rows, start=1)]

    @rx.var(cache=True)
    def total_shown(self) -> int:
        return len(self.filtered_coins)

    @rx.var(cache=True)
    def total_pages(self) -> int:
        return max(1, -(-self.total_shown // self.page_size))

    @rx.var(cache=True)
    def skeleton_rows(self) -> list[int]:
        """One entry per skeleton row to render while is_filtering is true
        — sized to page_size (not a fixed count) so the skeleton matches
        whatever row count the real table is about to show. Errs toward
        page_size even on a short last page/search result rather than a
        smaller count, so the page height never visibly collapses then
        re-expands once the real (possibly shorter) rows replace it.
        """
        return list(range(self.page_size))

    @rx.var(cache=True)
    def page_top_n(self) -> int:
        """The table title's "Top N" — page 1 is 100, page 2 is 200, and so
        on, capped to how many coins are actually in view (so a narrow
        narrative filter doesn't claim "Top 100" when there are only 20).
        """
        return min(self.page * self.page_size, self.total_shown)

    @rx.var(cache=True)
    def paged_coins(self) -> list[dict]:
        start = (self.page - 1) * self.page_size
        return self.filtered_coins[start : start + self.page_size]

    @rx.var(cache=True)
    def sorted_paged_coins(self) -> list[dict]:
        """The current page's rows, optionally re-sorted by one column.
        Only ever reorders within this page (top 100, or whichever 100
        the current page is) — never re-ranks across the full coin list.
        """
        rows = self.paged_coins
        if not self.sort_key:
            return rows
        return sorted(
            rows, key=lambda r: r[self.sort_key], reverse=self.sort_direction == "desc"
        )

    @rx.var(cache=True)
    def page_str(self) -> str:
        return str(self.page)

    @rx.var(cache=True)
    def active_page_str(self) -> str:
        return str(self.active_page)

    @rx.var(cache=True)
    def page_size_str(self) -> str:
        return str(self.page_size)

    @rx.var(cache=True)
    def showing_start(self) -> int:
        return 0 if self.total_shown == 0 else (self.page - 1) * self.page_size + 1

    @rx.var(cache=True)
    def showing_end(self) -> int:
        return min(self.page * self.page_size, self.total_shown)

    @rx.var(cache=True)
    def page_window(self) -> list[str]:
        """Page numbers to render, e.g. ["1","2","3","4","5","...","117"] —
        a leading run around the current page, plus the last page, with
        "..." marking any gap. "..." entries render as plain text, not
        buttons (see coin_table.py::_page_number).
        """
        total = self.total_pages
        current = self.page
        if total <= 7:
            window = list(range(1, total + 1))
        elif current <= 5:
            window = list(range(1, 6))
        elif current >= total - 4:
            window = list(range(total - 4, total + 1))
        else:
            window = list(range(current - 2, current + 3))

        pages: list[str] = []
        if window[0] > 1:
            pages.append("1")
            if window[0] > 2:
                pages.append("...")
        pages.extend(str(p) for p in window)
        if window[-1] < total:
            if window[-1] < total - 1:
                pages.append("...")
            pages.append(str(total))
        return pages
