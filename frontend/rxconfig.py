import reflex as rx

config = rx.Config(
    app_name="frontend",
    db_url="sqlite:///reflex.db",
    # Per explicit request — the app has its own floating brand badge now
    # (frontend.py::_floating_logo), so Reflex's own "Built with Reflex"
    # sticky badge (reflex/compiler/compiler.py::_setup_sticky_badge, only
    # ever injected in prod mode) is redundant/unwanted clutter in the same
    # corner. None (the default) shows it based on Reflex's own referrer
    # heuristics; False always hides it.
    show_built_with_reflex=False,
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
        rx.plugins.RadixThemesPlugin(theme=rx.theme(appearance="dark", accent_color="indigo")),
    ]
)