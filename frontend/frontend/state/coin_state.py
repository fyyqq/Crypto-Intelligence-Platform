"""State for the coin list page: loads the cached CoinMarketCap data and
exposes a narrative filter, backed by the SQLModel tables in frontend/models.
"""

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


class CoinState(rx.State):
    all_coins: list[dict] = []
    categories: list[str] = []
    selected_category: str = "All narratives"
    is_loading: bool = True
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
                .options(selectinload(Coin.categories))
                .order_by(Coin.cmc_rank)
            ).all()

            rows: list[dict] = []
            narrative_names: set[str] = set()
            for coin in coins:
                names = sorted(category.name for category in coin.categories)
                narrative_names.update(names)
                trend_24h_data, trend_24h_color, trend_24h_shine = _trend_line(coin.percent_change_24h or 0.0)
                trend_7d_data, trend_7d_color, trend_7d_shine = _trend_line(coin.percent_change_7d or 0.0)
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
                        "trend_24h_data": trend_24h_data,
                        "trend_24h_color": trend_24h_color,
                        "trend_24h_shine": trend_24h_shine,
                        "trend_7d_data": trend_7d_data,
                        "trend_7d_color": trend_7d_color,
                        "trend_7d_shine": trend_7d_shine,
                    }
                )

        self.all_coins = rows
        self.categories = ["All narratives", *sorted(narrative_names)]
        self.is_loading = False

    @rx.event
    def set_category(self, value: str):
        self.selected_category = value
        self.page = 1
        self.sort_key = ""
        self.sort_direction = ""

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
