"""State for /tools/multichart: the chart cards on the page.

The page starts with one empty card (a + in the middle); the full-width "Add more chart" button adds another (up to
MAX_CARDS) and, once there is more than one card, every card has an x that removes it (the last card can't be removed).
Clicking the + opens a coin search inside that card (the same name / ticker match, CMC rank order and result rows as the
header search); clicking a coin shows its TradingView chart in the card. The chart symbol is found the way the coin page
finds it (a hand-picked chart, else the coin's own CEX pairs in the MEXC > KuCoin > HTX > Bybit order, else the DEX /
TradingView Crypto-tab lookup), so a card always charts the same pair as that coin's page. A coin with no chart anywhere
says so. Nothing is saved: a fresh visit starts again with one empty card."""

import asyncio

import reflex as rx

from frontend.state.coin_state import (
    CoinState,
    _fetch_market_pairs,
    _fetch_tradingview_dex_symbol,
    _format_market_pairs,
    _rank_order,
    _resolve_chart_symbol,
    _search_fields,
    tradingview_widget_src,
)

MAX_CARDS = 12
SEARCH_LIMIT = 20


def _empty_card(card_id: int) -> dict:
    return {
        "id": card_id, "status": "empty",  # empty | loading | ready | nochart
        "cmc_id": 0, "name": "", "symbol": "", "icon_url": "", "chart_symbol": "",
        "iframe_light": "", "iframe_dark": "", "message": "",
    }


def search_coins(rows: list[dict], query: str, merge) -> list[dict]:
    """The coins whose name or ticker contains `query` (exact ticker first, then CMC rank order), as search rows.
    `merge` applies the live overrides (price / change) to a row; it is only run on the rows that are kept."""
    q = query.strip().lower()
    if not q:
        return []
    hits = [r for r in rows if q in r["name"].lower() or q in r["symbol"].lower()]
    hits.sort(key=lambda r: (r["symbol"].lower() != q, _rank_order(r)))
    return [_search_fields(merge(r)) for r in hits[:SEARCH_LIMIT]]


def find_chart_symbol(row: dict) -> str | None:
    """The TradingView symbol for one coin row (blocking: may read Postgres / the exchange pair lists), or None."""
    symbol = _resolve_chart_symbol(row["symbol"], row)
    if symbol:
        return symbol
    result = _fetch_market_pairs(row["symbol"], row["cmc_id"])
    if result is not None:
        _cmc_id, pairs = result
        symbol = _resolve_chart_symbol(row["symbol"], {**row, "market_pairs": _format_market_pairs(pairs)})
        if symbol:
            return symbol
    dex = _fetch_tradingview_dex_symbol(row["symbol"], row["cmc_id"])  # no CEX pair at all: the DEX / Crypto-tab listing
    return dex[1] if dex and dex[1] else None


class MultichartState(rx.State):
    cards: list[dict] = [_empty_card(1)]
    next_id: int = 2
    search_card: int = 0  # the card whose coin search is open (0 = none)
    search_query: str = ""
    search_results: list[dict] = []

    @rx.var
    def can_add(self) -> bool:
        return len(self.cards) < MAX_CARDS

    @rx.var
    def can_remove(self) -> bool:
        return len(self.cards) > 1

    def _update_card(self, card_id: int, changes: dict) -> None:
        self.cards = [{**c, **changes} if c["id"] == card_id else c for c in self.cards]

    @rx.event
    def reset_cards(self):
        """A fresh visit starts with a single empty card."""
        self.cards = [_empty_card(1)]
        self.next_id = 2
        self.search_card = 0
        self.search_query = ""
        self.search_results = []

    @rx.event
    def add_card(self):
        if len(self.cards) < MAX_CARDS:
            self.cards = [*self.cards, _empty_card(self.next_id)]
            self.next_id += 1

    @rx.event
    def remove_card(self, card_id: int):
        if len(self.cards) > 1:
            self.cards = [c for c in self.cards if c["id"] != card_id]
            if self.search_card == card_id:
                self.search_card = 0

    @rx.event
    def open_search(self, card_id: int):
        self.search_card = card_id
        self.search_query = ""
        self.search_results = []

    @rx.event
    def close_search(self):
        self.search_card = 0

    @rx.event
    async def search(self, query: str):
        self.search_query = query.strip()
        if not self.search_query:
            self.search_results = []
            return
        coins = await self.get_state(CoinState)
        self.search_results = search_coins(coins._all_coins, self.search_query, coins._row_with_overrides)

    @rx.event(background=True)
    async def choose_coin(self, card_id: int, cmc_id: int):
        """A coin was clicked in a card's search: show its chart there (the symbol lookup runs off the event loop)."""
        async with self:
            coins = await self.get_state(CoinState)
            base = next((r for r in coins._all_coins if r["cmc_id"] == cmc_id), None)
            if base is None or not any(c["id"] == card_id for c in self.cards):
                return
            row = coins._row_with_overrides(base)
            self._update_card(card_id, {
                "status": "loading", "cmc_id": cmc_id, "name": row["name"], "symbol": row["symbol"],
                "icon_url": row.get("icon_url") or "", "chart_symbol": "", "iframe_light": "", "iframe_dark": "", "message": "",
            })
            self.search_card = 0
            self.search_results = []
        try:
            chart_symbol = await asyncio.to_thread(find_chart_symbol, row)
            failed = False
        except Exception:  # the lookup reads Postgres and the network: a failure must not break the page
            chart_symbol, failed = None, True
        async with self:
            card = next((c for c in self.cards if c["id"] == card_id), None)
            if card is None or card["cmc_id"] != cmc_id:  # removed, or another coin was picked meanwhile
                return
            if chart_symbol:
                self._update_card(card_id, {
                    "status": "ready", "chart_symbol": chart_symbol,
                    "iframe_light": tradingview_widget_src(chart_symbol, "light"),
                    "iframe_dark": tradingview_widget_src(chart_symbol, "dark"),
                })
            else:
                self._update_card(card_id, {
                    "status": "nochart",
                    "message": "The chart could not be loaded right now. Try again." if failed else f"No live chart is available for {row['name']} yet.",
                })
