"""State for the coin list page: loads the cached CoinMarketCap data and
exposes a narrative filter, backed by the SQLModel tables in frontend/models.
"""

import reflex as rx
from sqlalchemy.orm import selectinload
from sqlmodel import select

from frontend.models.coin import Coin


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
    return names[0] if names else "—"


class CoinState(rx.State):
    all_coins: list[dict] = []
    categories: list[str] = []
    selected_category: str = "All narratives"
    is_loading: bool = True
    page: int = 1
    page_size: int = 50

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
                rows.append(
                    {
                        "name": coin.name,
                        "symbol": coin.symbol,
                        "icon_url": f"https://s2.coinmarketcap.com/static/img/coins/64x64/{coin.cmc_id}.png",
                        "market_cap_usd": coin.market_cap_usd or 0.0,
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
                        "primary_narrative": _pick_primary_narrative(names),
                    }
                )

        self.all_coins = rows
        self.categories = ["All narratives", *sorted(narrative_names)]
        self.is_loading = False

    @rx.event
    def set_category(self, value: str):
        self.selected_category = value
        self.page = 1

    @rx.event
    def next_page(self):
        if self.page < self.total_pages:
            self.page += 1

    @rx.event
    def prev_page(self):
        if self.page > 1:
            self.page -= 1

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
