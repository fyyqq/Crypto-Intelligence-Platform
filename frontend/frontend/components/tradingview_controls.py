import reflex as rx

_TIMEFRAMES = (
    ("1m", "1"),
    ("5m", "5"),
    ("15m", "15"),
    ("1h", "60"),
    ("4h", "240"),
    ("D", "D"),
    ("W", "W"),
)


def timeframe_controls(default_interval: str, hidden: bool = False) -> rx.Component:
    """The 1m..W buttons under a TradingView chart. `hidden` keeps them in the page (their click
    handler, tradingview_timeframes.js, still works) but invisible: opacity 0, width 0, height 0, as
    requested for the coin page (2026-10-15); overflow hidden so the zero-size box also clips and
    cannot be clicked, and position absolute so it takes no room in whatever stack it sits in."""
    return rx.hstack(
        *[
            rx.el.button(
                label,
                type="button",
                class_name="tv-timeframe-button",
                custom_attrs={
                    "data-tv-interval": interval,
                    "aria-pressed": "true" if interval == default_interval else "false",
                },
            )
            for label, interval in _TIMEFRAMES
        ],
        role="group",
        aria_label="Chart timeframe",
        class_name="tv-timeframe-controls",
        spacing="1",
        wrap="wrap",
        **({"style": {"opacity": 0, "width": 0, "height": 0, "overflow": "hidden", "position": "absolute", "pointerEvents": "none"}} if hidden else {}),
    )