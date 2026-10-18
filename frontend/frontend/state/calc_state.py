"""State for the two calculator tools (/tools/profit-calculator and /tools/currency-converter): only the live
USD -> MYR rate. The arithmetic itself runs in the browser (assets/calculators.js) so every keystroke answers at once;
this state keeps the rate fresh (read through app/services/fx_service.py: Yahoo Finance polled every 60 s plus two
daily references, a quote far from the others is dropped) and hands it to the page as data attributes."""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import reflex as rx

_ROOT = str(Path(__file__).resolve().parent.parent.parent.parent)
_KL = ZoneInfo("Asia/Kuala_Lumpur")
REFRESH_SECONDS = 30  # the rate service caches Yahoo for 60 s, so this only re-reads its copy


def _fx():
    # APPENDED, not inserted first (see gainers_losers_state._service).
    if _ROOT not in sys.path:
        sys.path.append(_ROOT)
    from app.services import fx_service

    return fx_service


def rate_view(info: dict | None) -> dict[str, str]:
    """The page's strings for one fx_service rate dict (None = no usable rate)."""
    if not info:
        return {"rate": "", "note": "", "time": "", "error": "The live USD / MYR rate is unavailable right now. Try again in a moment."}
    stamp = datetime.fromtimestamp(info["as_of"], _KL).strftime("%d %b %H:%M:%S")
    return {"rate": f"{info['rate']:.6f}", "note": info["note"], "time": f"{stamp} (KL)", "error": ""}


class CalcState(rx.State):
    fx_rate: str = ""  # USD -> MYR, e.g. "4.079500"; "" until the first read
    fx_note: str = ""  # "Yahoo Finance · live"
    fx_time: str = ""  # when the quote was made
    fx_error: str = ""
    _watching: bool = False

    async def _read(self) -> None:
        info = await asyncio.to_thread(_fx().get_rate, "MYR")  # cached, blocking, never raises
        view = rate_view(info)
        async with self:
            if view["rate"] or not self.fx_rate:  # a failed read never wipes a rate already shown
                self.fx_rate, self.fx_note, self.fx_time = view["rate"], view["note"], view["time"]
            self.fx_error = view["error"] if not self.fx_rate else ""

    @rx.event(background=True)
    async def load_rate(self):
        """on_load of both calculator pages: read the rate now, then keep it fresh while the tab is open."""
        await self._read()
        from frontend.frontend import app as reflex_app

        async with self:
            if self._watching:
                return
            self._watching = True
        try:
            while True:
                await asyncio.sleep(REFRESH_SECONDS)
                async with self:
                    gone = self.router.session.client_token not in reflex_app.event_namespace.token_to_sid
                if gone:
                    break
                await self._read()
        finally:
            async with self:
                self._watching = False
