"""The Telegram calculators: /currency_converter and /pnl_calculator (the same maths as the website's Profit Calculator
and Currency Converter tools, assets/calculators.js). USD and MYR only, at the live rate from fx_service.

    /currency-converter $1000      -> $1,000.00 = RM4,079.00          ($ converts to MYR)
    /currency-converter RM1000     -> RM1,000.00 = $245.16            (RM converts to USD)
    /pnl-calculator $1000 + 50%    -> $1,000.00 + 50% = $1,500.00
    /pnl-calculator RM4000 - 25%   -> RM4,000.00 - 25% = RM3,000.00   (the currency of the capital is the result's)

Braces from the usage templates ({RM1000}, ${$1000}) are tolerated. A number with no symbol counts as USD, the site's
default currency. Telegram's menu cannot hold a hyphen, so the menu names use underscores; the hyphen spelling typed by
hand works too (handle_message maps it)."""

from __future__ import annotations

import html
import re

from app.services import fx_service as fx

CONVERTER_USAGE = "Usage: /currency-converter $1000 (to ringgit) or /currency-converter RM1000 (to dollars)"
PNL_USAGE = "Usage: /pnl-calculator $1000 + 50% or /pnl-calculator RM4000 - 25% (the sign is + for profit, - for loss)"

_NUM = r"(?:\d[\d,]*(?:\.\d+)?|\.\d+)"
_MONEY = re.compile(rf"^\$?(?P<cur>\$|rm|usd|myr)?\s*(?P<num>{_NUM})$", re.I)
_PCT = re.compile(r"^(?P<num>\d[\d,]*(?:\.\d+)?|\.\d+)\s*%?$")


def _clean(text: str) -> str:
    """Drops the template braces and a doubled $ ("${$1000}" -> "$1000")."""
    return re.sub(r"\$+", "$", text.replace("{", "").replace("}", "")).strip()


def parse_money(text: str) -> tuple[str, float] | None:
    """"$1000" -> ("USD", 1000.0); "RM1,000.50" -> ("MYR", 1000.5); "1000" -> ("USD", 1000.0). None when not an amount."""
    m = _MONEY.match(_clean(text))
    if not m:
        return None
    cur = (m.group("cur") or "$").lower()
    return ("MYR" if cur in ("rm", "myr") else "USD"), float(m.group("num").replace(",", ""))


def other(cur: str) -> str:
    return "MYR" if cur == "USD" else "USD"


def convert(amount: float, from_cur: str, rate: float) -> float:
    """`rate` = MYR per 1 USD."""
    return amount * rate if from_cur == "USD" else amount / rate


def profit(capital: float, pct: float, sign: int) -> dict:
    """{change, result, pct, clamped}: a loss of more than 100% is counted as 100%."""
    clamped = sign < 0 and pct > 100
    p = 100.0 if clamped else pct
    change = capital * p / 100 * (-1 if sign < 0 else 1)
    return {"change": change, "result": capital + change, "pct": p, "clamped": clamped}


def _rate() -> tuple[float, dict] | None:
    info = fx.get_rate("MYR")  # blocking, cached 60 s, never raises
    return (info["rate"], info) if info else None


def _pct_text(v: float) -> str:
    return f"{v:,.4f}".rstrip("0").rstrip(".")


def _rate_lines(rate: float, info: dict) -> str:
    return (
        f"1 USD = {rate:,.4f} MYR · 1 MYR = {1 / rate:,.4f} USD\n"
        f"<i>Live mid-market rate · {html.escape(info['note'])}</i>"
    )


UNAVAILABLE = "The live USD / MYR rate is unavailable right now. Try again in a moment."


def converter_message(arg: str) -> str:
    """The /currency_converter reply for the text after the command."""
    parsed = parse_money(arg)
    if parsed is None:
        return CONVERTER_USAGE
    cur, amount = parsed
    got = _rate()
    if got is None:
        return UNAVAILABLE
    rate, info = got
    to = other(cur)
    return (
        f"💱 <b>{fx.format_amount(amount, cur)} = {fx.format_amount(convert(amount, cur, rate), to)}</b>\n"
        + _rate_lines(rate, info)
    )


def parse_pnl(text: str) -> tuple[str, float, int, float] | None:
    """"$1000 + 50%" -> ("USD", 1000.0, 1, 50.0); also "$1000 +50%", "RM4000 - 25", "$1000 -50%", and the usage
    template typed as it is ("${$1000} ${+} ${50%}"). None when not understood."""
    tokens = _clean(text).split()
    tokens[1:] = [t.lstrip("$") for t in tokens[1:]]  # a $ left over from "${+}" / "${50%}"
    m = re.match(
        rf"^(?P<cap>\$?(?:rm|usd|myr)?\s?{_NUM})\s*(?P<sign>[+\-−–])\s*(?P<pct>{_NUM}\s*%?)$", " ".join(tokens), re.I
    )
    if not m:
        return None
    money = parse_money(m.group("cap"))
    pct = _PCT.match(m.group("pct").strip())
    if money is None or pct is None:
        return None
    return money[0], money[1], (1 if m.group("sign") == "+" else -1), float(pct.group("num").replace(",", ""))


def pnl_message(arg: str) -> str:
    """The /pnl_calculator reply for the text after the command."""
    parsed = parse_pnl(arg)
    if parsed is None:
        return PNL_USAGE
    cur, capital, sign, pct = parsed
    r = profit(capital, pct, sign)
    money = lambda v: fx.format_amount(v, cur)  # noqa: E731
    signed = lambda v, c=cur: fx.format_amount(v, c, signed=True)  # noqa: E731
    op = "-" if sign < 0 else "+"
    lines = [
        f"{'📉' if sign < 0 else '📈'} <b>{money(r['result'])}</b>",
        f"{money(capital)} {op} {_pct_text(r['pct'])}% = {money(r['result'])}",
        f"{'Loss' if sign < 0 else 'Profit'} {signed(r['change'])} ({op}{_pct_text(r['pct'])}%)",
    ]
    if r["clamped"]:
        lines.append("⚠️ A loss can't be more than 100%, so it is counted as 100%.")
    got = _rate()
    if got is not None:
        rate, info = got
        o = other(cur)
        lines += ["", f"In {o}: <b>{fx.format_amount(convert(r['result'], cur, rate), o)}</b> ({signed(convert(r['change'], cur, rate), o)})", _rate_lines(rate, info)]
    return "\n".join(lines)
