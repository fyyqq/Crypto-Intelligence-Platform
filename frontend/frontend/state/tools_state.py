"""State for the /tools page: Fear & Greed, Altcoin/Bitcoin Season and the
BTC/ETH rainbow chart (the TradingView-embed sections need no state).

Data comes from app/services/market_tools_service.py. Each tool with more
than one data source keeps the viewer's choice in the browser (LocalStorage)
and shows a popup listing the sources with their .env key status; a source
whose key is missing asks the viewer to add it to .env.
"""

import asyncio
import sys
from pathlib import Path
from typing import Any

import reflex as rx

_ROOT = str(Path(__file__).resolve().parent.parent.parent.parent)

_TOOL_TITLES = {"fng": "Fear & Greed Index", "season": "Altcoin / Bitcoin Season"}


def _service():
    # Reflex's process only has frontend/ on sys.path; the project root is
    # needed before `app.*` imports (same pattern as the other states).
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    from app.services import market_tools_service

    return market_tools_service


def _fng_color(value: int) -> str:
    if value < 25:
        return "#ea3943"
    if value < 45:
        return "#ea8c00"
    if value < 55:
        return "#d6b800"
    if value < 75:
        return "#93d900"
    return "#16c784"


def _fng_text(point: dict) -> str:
    return f"{point['value']} · {point['label']}" if point["value"] >= 0 else "—"


class ToolsState(rx.State):
    # The viewer's chosen data source per tool ("" = automatic).
    fng_source: str = rx.LocalStorage("", name="repace_tools_fng_source")
    season_source: str = rx.LocalStorage("", name="repace_tools_season_source")

    # Source popup: which tool's dialog is open ("" = closed), and its rows.
    dialog_tool: str = ""
    dialog_options: list[dict[str, Any]] = []

    # Fear & Greed
    fng_loading: bool = True
    fng_error: str = ""
    fng_key_missing: bool = False
    fng_key_env: str = ""
    fng_value: int = 0
    fng_label: str = ""
    fng_color: str = "#d6b800"
    fng_updated: str = ""
    fng_source_name: str = ""
    fng_gauge: str = ""
    fng_yesterday: str = ""
    fng_week: str = ""
    fng_month: str = ""

    # Altcoin / Bitcoin season
    season_loading: bool = True
    season_error: str = ""
    season_key_missing: bool = False
    season_key_env: str = ""
    season_index: int = 0
    season_label: str = ""
    season_beat: int = 0
    season_total: int = 0
    season_window: str = ""
    season_btc_change: str = ""
    season_source_name: str = ""
    season_best: list[dict[str, str]] = []

    # Rainbow chart
    rainbow_asset: str = "BTC"
    rainbow_loading: bool = True
    rainbow_error: str = ""
    rainbow_svg: str = ""
    rainbow_price: str = ""
    rainbow_band: str = ""
    rainbow_band_color: str = ""
    rainbow_asof: str = ""
    rainbow_legend: list[dict[str, str]] = []

    @rx.var
    def dialog_title(self) -> str:
        return _TOOL_TITLES.get(self.dialog_tool, "")

    @rx.var
    def dialog_open(self) -> bool:
        return self.dialog_tool != ""

    @rx.var
    def fng_marker_left(self) -> str:
        return f"{self.fng_value}%"

    @rx.var
    def season_marker_left(self) -> str:
        return f"{self.season_index}%"

    # ---- source popup ------------------------------------------------
    def _chosen(self, tool: str) -> str:
        return self.fng_source if tool == "fng" else self.season_source

    def _build_options(self, tool: str) -> list[dict[str, Any]]:
        svc = _service()
        active, _ = svc.resolve_source(tool, self._chosen(tool))
        return [{**o, "selected": o["id"] == active} for o in svc.source_status(tool)]

    @rx.event
    def open_source_dialog(self, tool: str):
        self.dialog_options = self._build_options(tool)
        self.dialog_tool = tool

    @rx.event
    def dialog_open_change(self, is_open: bool):
        if not is_open:
            self.dialog_tool = ""

    @rx.event
    def recheck_keys(self):
        """Re-read .env (a key may have just been added) and refresh."""
        if self.dialog_tool:
            self.dialog_options = self._build_options(self.dialog_tool)
        return [ToolsState.refresh_fng, ToolsState.refresh_season]

    @rx.event
    def choose_source(self, source_id: str):
        tool = self.dialog_tool
        if tool == "fng":
            self.fng_source = source_id
        elif tool == "season":
            self.season_source = source_id
        self.dialog_options = self._build_options(tool)
        return ToolsState.refresh_fng if tool == "fng" else ToolsState.refresh_season

    # ---- loaders -----------------------------------------------------
    @rx.event(background=True)
    async def refresh_fng(self):
        svc = _service()
        async with self:
            source, missing = svc.resolve_source("fng", self.fng_source)
            self.fng_loading = not missing
            self.fng_error = ""
            self.fng_key_missing = missing
            if missing:
                self.fng_key_env = next(o["env"] for o in svc.source_status("fng") if o["id"] == source)
                if not self.dialog_tool:
                    self.dialog_options = self._build_options("fng")
                    self.dialog_tool = "fng"
        if missing:
            return
        try:
            data = await asyncio.to_thread(svc.get_fear_greed, source)
            gauge = svc.fng_gauge_svg(data["value"])
        except svc.ToolsDataError as exc:
            async with self:
                self.fng_loading = False
                self.fng_error = str(exc)
            return
        async with self:
            self.fng_value = data["value"]
            self.fng_label = data["label"]
            self.fng_color = _fng_color(data["value"])
            self.fng_updated = data["updated"]
            self.fng_source_name = data["source"]
            self.fng_gauge = gauge
            self.fng_yesterday = _fng_text(data["yesterday"])
            self.fng_week = _fng_text(data["week"])
            self.fng_month = _fng_text(data["month"])
            self.fng_loading = False

    @rx.event(background=True)
    async def refresh_season(self):
        svc = _service()
        async with self:
            source, missing = svc.resolve_source("season", self.season_source)
            self.season_loading = not missing
            self.season_error = ""
            self.season_key_missing = missing
            if missing:
                self.season_key_env = next(o["env"] for o in svc.source_status("season") if o["id"] == source)
                if not self.dialog_tool:
                    self.dialog_options = self._build_options("season")
                    self.dialog_tool = "season"
        if missing:
            return
        try:
            data = await asyncio.to_thread(svc.get_altcoin_season, source)
        except svc.ToolsDataError as exc:
            async with self:
                self.season_loading = False
                self.season_error = str(exc)
            return
        async with self:
            self.season_index = data["index"]
            self.season_label = data["label"]
            self.season_beat = data["beat"]
            self.season_total = data["total"]
            self.season_window = data["window"]
            self.season_btc_change = data["btc_change"]
            self.season_source_name = data["source"]
            self.season_best = data["best"]
            self.season_loading = False

    @rx.event(background=True)
    async def refresh_rainbow(self):
        svc = _service()
        async with self:
            asset = self.rainbow_asset
            self.rainbow_loading = True
            self.rainbow_error = ""
        try:
            data = await asyncio.to_thread(svc.get_rainbow, asset)
        except svc.ToolsDataError as exc:
            async with self:
                self.rainbow_loading = False
                self.rainbow_error = str(exc)
            return
        async with self:
            if self.rainbow_asset != asset:  # viewer switched tab meanwhile
                return
            self.rainbow_svg = data["svg"]
            self.rainbow_price = data["price"]
            self.rainbow_band = data["band"]
            self.rainbow_band_color = data["band_color"]
            self.rainbow_asof = data["asof"]
            self.rainbow_legend = data["legend"]
            self.rainbow_loading = False

    @rx.event
    def set_rainbow_asset(self, asset: str):
        if asset == self.rainbow_asset:
            return
        self.rainbow_asset = asset
        return ToolsState.refresh_rainbow
