"""State for the coin list page: loads the cached CoinMarketCap data and
exposes a narrative filter, backed by the SQLModel tables in frontend/models.
"""

from collections import Counter

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
    return f"${value:,.2f}" if value < 1 else f"${value:,.0f}"


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
    page_size: int = 100

    # In-page sort only: reorders the current page's rows, never re-ranks
    # across the full coin list. sort_key is one of the raw numeric fields
    # in each row dict (e.g. "pct_1h_raw"), or "" for the default (market-cap)
    # order. sort_direction cycles "desc" (1st click, biggest -> smallest, top
    # arrow active) -> "asc" (2nd click, smallest -> biggest, bottom arrow
    # active) -> neutral (3rd click, both "", back to default order).
    # Changing page also resets both, per spec.
    sort_key: str = ""
    sort_direction: str = ""

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
                names = sorted(category.name for category in coin.categories)
                narrative_counts.update(names)
                trend_24h_data, trend_24h_color, trend_24h_shine = _trend_line(coin.percent_change_24h or 0.0)
                trend_7d_data, trend_7d_color, trend_7d_shine = _trend_line(coin.percent_change_7d or 0.0)
                primary_narrative = _pick_primary_narrative(names)

                # A coin with no contract rows is single-chain — it IS its
                # own chain. Otherwise the row already flagged as primary
                # (see MarketDataService._upsert_contracts) is the main
                # chain; everything else feeds the "other chains" dropdown.
                chains = sorted(coin.contracts, key=lambda c: c.sort_order)
                primary_chain = next((c for c in chains if c.is_primary), None)
                main_chain = primary_chain.platform_name if primary_chain else coin.name
                other_chains = [c.platform_name for c in chains if c is not primary_chain]
                chain_counts.update([main_chain])

                rows.append(
                    {
                        "name": coin.name,
                        "symbol": coin.symbol,
                        "icon_url": f"https://s2.coinmarketcap.com/static/img/coins/64x64/{coin.cmc_id}.png",
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
                        "primary_narrative": primary_narrative,
                        "primary_narrative_icon": _narrative_icon(primary_narrative),
                        "main_chain": main_chain,
                        "other_chains_display": "\n".join(other_chains),
                        "has_other_chains": len(other_chains) > 0,
                        "trend_24h_data": trend_24h_data,
                        "trend_24h_color": trend_24h_color,
                        "trend_24h_shine": trend_24h_shine,
                        "trend_7d_data": trend_7d_data,
                        "trend_7d_color": trend_7d_color,
                        "trend_7d_shine": trend_7d_shine,
                    }
                )

        self.all_coins = rows
        # Top 10 by number of coins carrying that tag — out of ~600 dynamic
        # CMC categories, this keeps the filter pill bar to the narratives
        # that actually matter for most coins shown, not an alphabetical cut.
        top_narratives = [name for name, _ in narrative_counts.most_common(10)]
        self.categories = ["All narratives", *top_narratives]
        # Top 10 chains by number of coins whose primary/native chain it is
        # — same "most common" approach as narratives, dynamically computed
        # each sync rather than a fixed chain list.
        top_chains = [name for name, _ in chain_counts.most_common(10)]
        self.chains = ["All chains", *top_chains]
        self.is_loading = False

    @rx.event
    def set_category(self, value: str):
        # active_category has no dependent computed vars, so this first
        # flush (pill turns blue + skeleton shows) is instant. Only the
        # second flush, after the actual re-filter/re-sort runs, updates
        # selected_category — that's the part with a noticeable round trip.
        self.active_category = value
        self.is_filtering = True
        yield
        self.selected_category = value
        self.page = 1
        self.sort_key = ""
        self.sort_direction = ""
        self.is_filtering = False

    @rx.event
    def set_chain(self, value: str):
        # Same instant-highlight-then-refilter pattern as set_category. The
        # two filters combine with AND (see filtered_coins) — narrative +
        # chain together, e.g. "Memes" + "BNB Smart Chain (BEP20)".
        self.active_chain = value
        self.is_filtering = True
        yield
        self.selected_chain = value
        self.page = 1
        self.sort_key = ""
        self.sort_direction = ""
        self.is_filtering = False

    @rx.event
    def next_page(self):
        if self.page < self.total_pages:
            self.page += 1
            self.sort_key = ""
            self.sort_direction = ""

    @rx.event
    def prev_page(self):
        if self.page > 1:
            self.page -= 1
            self.sort_key = ""
            self.sort_direction = ""

    @rx.event
    def go_to_page(self, page_str: str):
        page = int(page_str)
        if 1 <= page <= self.total_pages:
            self.page = page
            self.sort_key = ""
            self.sort_direction = ""

    @rx.event
    def set_page_size(self, value: str):
        self.page_size = int(value)
        self.page = 1
        self.sort_key = ""
        self.sort_direction = ""

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
