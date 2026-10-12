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
    # Session state in memory, not pickled to frontend/.states/ on every
    # change: a coin-page session was a ~22 MB pickle rewritten on each event
    # (every 1s live price tick, every 30s price refresh). Safe because the app
    # runs a single backend worker (local and live); with several workers this
    # would need redis instead. Sessions are lost on restart (they log back in
    # via the cookie / dev auto-login).
    state_manager_mode=rx.constants.StateManagerMode.MEMORY,
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
        rx.plugins.RadixThemesPlugin(theme=rx.theme(appearance="dark", accent_color="indigo")),
    ]
)