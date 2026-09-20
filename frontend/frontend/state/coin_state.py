"""State for the coin list page: loads the cached CoinMarketCap data and
exposes a narrative filter, backed by the SQLModel tables in frontend/models.
"""

import reflex as rx
from sqlalchemy.orm import selectinload
from sqlmodel import select

from frontend.models.coin import Coin


def _fmt_usd(value: float) -> str:
    return f"${value:,.2f}" if value < 1 else f"${value:,.0f}"


def _fmt_pct(value: float) -> str:
    return f"{value:+.2f}%"


def _pct_color(value: float) -> str:
    return "red" if value < 0 else "green"


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
                        "rank": coin.cmc_rank or 0,
                        "name": coin.name,
                        "symbol": coin.symbol,
                        "market_cap_usd": coin.market_cap_usd or 0.0,
                        "price_display": _fmt_usd(coin.price_usd or 0.0),
                        "market_cap_display": _fmt_usd(coin.market_cap_usd or 0.0),
                        "volume_display": _fmt_usd(coin.volume_24h_usd or 0.0),
                        "change_1h_display": _fmt_pct(coin.percent_change_1h or 0.0),
                        "change_1h_color": _pct_color(coin.percent_change_1h or 0.0),
                        "change_24h_display": _fmt_pct(coin.percent_change_24h or 0.0),
                        "change_24h_color": _pct_color(coin.percent_change_24h or 0.0),
                        "change_7d_display": _fmt_pct(coin.percent_change_7d or 0.0),
                        "change_7d_color": _pct_color(coin.percent_change_7d or 0.0),
                        "narratives": ", ".join(names),
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
        return sorted(rows, key=lambda r: r["market_cap_usd"], reverse=True)

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
