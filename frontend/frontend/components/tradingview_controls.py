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


def timeframe_controls(default_interval: str) -> rx.Component:
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
    )