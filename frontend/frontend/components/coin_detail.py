"""Feature 2 (MVP): single-coin detail page, reached by clicking a row in
the homepage table. Three columns: [coin info, live chart, sentiment].

Per explicit scope for this pass — only the middle chart is real:
- Left column: real name/symbol/icon/price/rank (already cached from the
  homepage sync), everything else (FDV, supply, holders, profile score...)
  is static dummy placeholder data — no backend for this yet.
- Middle column: a real, live-updating TradingView chart (see
  CoinState.tradingview_iframe_src — CMC's free tier has no historical
  OHLCV endpoint, so this is the only way to show a genuinely real chart
  without a paid plan or a custom price-history pipeline).
- Right column: fully dummy sentiment/community placeholder data, no
  backend — mirrors the reference design's "Social Insights" panel.
"""

import reflex as rx

from frontend.components.footer import _BRAND_ICON_PATHS
from frontend.state import CoinState

# Dummy placeholder tag groups — CMC's categories API (CoinState.
# selected_coin's real narrative_list/platform_list) has no equivalent
# industry/self-reported sub-typing, so these two groups stay static.
_DUMMY_INDUSTRY_TAGS = ["AI & Big Data", "IoT", "Web3"]
_DUMMY_SELF_REPORTED_TAGS = ["PoS", "Platform", "Distributed Computing"]

# Each body is split before/after a "$<SYMBOL>" mention, filled in with
# whichever coin's page is open (see _post_card) — CoinState.selected_coin's
# symbol is a Var, so this can't just be one static f-string per post.
# "sentiment" drives that post's trending-up/down badge (green/positive vs
# red/negative, see _post_card) — 3 of the 10 are genuinely negative in
# tone, not just relabeled positive text, so the badge always matches what
# the post actually says. This same fixed 7-positive/3-negative dummy set
# is reused on every coin's page (only the "$<SYMBOL>" mention changes),
# so 24h Sentiment/Mindshare below are computed from it once, not per-coin.
_DUMMY_POSTS = [
    {
        "author": "CryptoWatcher",
        "handle": "@cryptowatcher",
        "time": "3h",
        "body_before": "",
        "body_after": " is moving again, and this time the bigger story is the market forming around it.",
        "likes": 128,
        "comments": 14,
        "reposts": 22,
        "sentiment": "positive",
    },
    {
        "author": "OnChainAlpha",
        "handle": "@onchainalpha",
        "time": "5h",
        "body_before": "Order book looks interesting on ",
        "body_after": " — liquidity has been quietly building up on the bid side all day.",
        "likes": 76,
        "comments": 6,
        "reposts": 9,
        "sentiment": "positive",
    },
    {
        "author": "WhaleAlertHQ",
        "handle": "@whalealerthq",
        "time": "6h",
        "body_before": "Large wallets just accumulated a fresh batch of ",
        "body_after": " — worth watching if this turns into a trend.",
        "likes": 203,
        "comments": 31,
        "reposts": 48,
        "sentiment": "positive",
    },
    {
        "author": "QuantSignals",
        "handle": "@quantsignals",
        "time": "8h",
        "body_before": "Momentum indicators on ",
        "body_after": " just flipped bullish on the 4h timeframe.",
        "likes": 95,
        "comments": 11,
        "reposts": 17,
        "sentiment": "positive",
    },
    {
        "author": "DeFiDegenz",
        "handle": "@defidegenz",
        "time": "9h",
        "body_before": "Community sentiment around ",
        "body_after": " has soured noticeably this week following the pullback in price.",
        "likes": 64,
        "comments": 8,
        "reposts": 5,
        "sentiment": "negative",
    },
    {
        "author": "ChainScopeIO",
        "handle": "@chainscopeio",
        "time": "11h",
        "body_before": "On-chain activity for ",
        "body_after": " is up sharply compared to last month's average.",
        "likes": 112,
        "comments": 19,
        "reposts": 14,
        "sentiment": "positive",
    },
    {
        "author": "MacroTraderX",
        "handle": "@macrotraderx",
        "time": "13h",
        "body_before": "",
        "body_after": " continues to hold key support even as broader markets chop sideways.",
        "likes": 87,
        "comments": 9,
        "reposts": 11,
        "sentiment": "positive",
    },
    {
        "author": "TokenMetricsFan",
        "handle": "@tokenmetricsfan",
        "time": "15h",
        "body_before": "Funding rates on ",
        "body_after": " perpetuals just flipped negative, signaling growing short pressure.",
        "likes": 58,
        "comments": 4,
        "reposts": 3,
        "sentiment": "negative",
    },
    {
        "author": "CryptoInsiderNews",
        "handle": "@cryptoinsidernews",
        "time": "18h",
        "body_before": "A wave of unconfirmed rumors around ",
        "body_after": " is spooking traders, and confidence looks shaky right now.",
        "likes": 145,
        "comments": 27,
        "reposts": 36,
        "sentiment": "negative",
    },
    {
        "author": "SatoshiScribe",
        "handle": "@satoshiscribe",
        "time": "22h",
        "body_before": "Long-term holders of ",
        "body_after": " don't seem fazed by the short-term volatility at all.",
        "likes": 71,
        "comments": 7,
        "reposts": 6,
        "sentiment": "positive",
    },
]

_POSITIVE_COUNT = sum(1 for p in _DUMMY_POSTS if p["sentiment"] == "positive")
_NEGATIVE_COUNT = len(_DUMMY_POSTS) - _POSITIVE_COUNT
# 0-10 scale (7 positive / 10 posts -> 7.00 green, 3 negative -> 3.00 red),
# shown as two side-by-side badges — matches the reference design's badge
# style, now split so both sides of the split are visible at once instead
# of only whichever side has the majority.
_SENTIMENT_SCORE_DISPLAY = f"{(_POSITIVE_COUNT / len(_DUMMY_POSTS) * 10):.2f}"
_SENTIMENT_COLOR = "green" if _POSITIVE_COUNT >= _NEGATIVE_COUNT else "red"
_NEGATIVE_SENTIMENT_SCORE_DISPLAY = f"{(_NEGATIVE_COUNT / len(_DUMMY_POSTS) * 10):.2f}"
# "Mindshare" as the exact count of sentiment posts analyzed (10, for this
# fixed dummy dataset) rather than an engagement-sum abbreviation — the
# request was for the exact amount of sentiment, not a compacted total.
_MINDSHARE_DISPLAY = str(len(_DUMMY_POSTS))


def _link_pill(
    *children: rx.Component,
    href: rx.Var[str] | str | None = None,
    on_click: rx.EventHandler | list[rx.EventHandler] | None = None,
    stacked: bool = False,
) -> rx.Component:
    # stacked=True lays the pill's content out as two lines (e.g. chain name,
    # then address+copy icon) instead of one long horizontal row — used for
    # the Contract pill, whose single-line "<chain name> <address> <copy
    # icon>" content overflowed its narrow 300px column for long chain names
    # (e.g. "BNB Smart Chain (BEP20)"). Since flex's own overflow anchors to
    # whichever edge justify-content points at, that overflow rendered as the
    # pill's left edge sliding underneath the row's own "Contract" label
    # instead of a clean wrap. Stacking keeps the pill's width bounded by
    # its widest single line (the chain name), which fits comfortably.
    pill = rx.flex(
        *children,
        direction="column" if stacked else "row",
        spacing="1",
        align="start" if stacked else "center",
        padding="0.3em 0.6em",
        border_radius="10px" if stacked else "9999px",
        background="var(--gray-a3)",
        flex_shrink="1" if stacked else "0",
        max_width="100%",
        # A copy-action pill (Contract: on_click, no href — nothing to
        # navigate away to) gets plain dark-in-light/white-in-dark text
        # instead — confirmed live that a hardcoded white here was
        # unreadable in light mode. A real link's color comes from
        # color_scheme="indigo" on the rx.link wrapper below instead
        # (same already-theme-correct pattern news_feed.py's "More News"
        # link uses), since a plain rx.flex has no equivalent of its own.
        **(
            {"color": rx.color_mode_cond(light="var(--gray-12)", dark="white")}
            if href is None and on_click is not None
            else {}
        ),
        **({"on_click": on_click, "cursor": "pointer"} if on_click is not None else {}),
    )
    if href is None:
        return pill
    return rx.link(pill, href=href, is_external=True, underline="none", color_scheme="indigo")


def _icon_circle(icon: rx.Component, size_px: str = "24px", href: rx.Var[str] | str | None = None) -> rx.Component:
    circle = rx.box(
        icon,
        width=size_px,
        height=size_px,
        border_radius="9999px",
        background="var(--gray-a3)",
        display="flex",
        align_items="center",
        justify_content="center",
        flex_shrink="0",
        # Dark-in-light/white-in-dark (not a hardcoded white, which was
        # unreadable in light mode) on every icon that's an actual clickable
        # link — the brand SVGs already hardcode their own fill so this is a
        # no-op for them, but lucide icons here (e.g. the Telegram "send"
        # icon) use stroke="currentColor" and pick this up.
        **({"color": rx.color_mode_cond(light="var(--gray-12)", dark="white")} if href is not None else {}),
    )
    if href is None:
        return circle
    return rx.link(circle, href=href, is_external=True)


def _link_row(label: str, *content: rx.Component) -> rx.Component:
    return rx.hstack(
        rx.text(label, size="2", color_scheme="gray", white_space="nowrap"),
        rx.hstack(*content, spacing="2", wrap="wrap", justify="end"),
        width="100%",
        align="center",
        justify="between",
        style={"row-gap": "0.4em"},
    )


_REDDIT_PATH = (
    "M12 0C5.373 0 0 5.373 0 12c0 3.314 1.343 6.314 3.515 8.485l-2.286 2.286C.775 23.225 1.097 24 1.738 24H12c6.627"
    " 0 12-5.373 12-12S18.627 0 12 0Zm4.388 3.199c1.104 0 1.999.895 1.999 1.999 0 1.105-.895 2-1.999 2-.946"
    " 0-1.739-.657-1.947-1.539v.002c-1.147.162-2.032 1.15-2.032 2.341v.007c1.776.067 3.4.567 4.686 1.363.473-.363"
    " 1.064-.58 1.707-.58 1.547 0 2.802 1.254 2.802 2.802 0 1.117-.655 2.081-1.601 2.531-.088 3.256-3.637"
    " 5.876-7.997 5.876-4.361 0-7.905-2.617-7.998-5.87-.954-.447-1.614-1.415-1.614-2.538 0-1.548 1.255-2.802"
    " 2.803-2.802.645 0 1.239.218 1.712.585 1.275-.79 2.881-1.291 4.64-1.365v-.01c0-1.663 1.263-3.034"
    " 2.88-3.207.188-.911.993-1.595 1.959-1.595Zm-8.085 8.376c-.784 0-1.459.78-1.506 1.797-.047 1.016.64 1.429"
    " 1.426 1.429.786 0 1.371-.369 1.418-1.385.047-1.017-.553-1.841-1.338-1.841Zm7.406 0c-.786 0-1.385.824-1.338"
    " 1.841.047 1.017.634 1.385 1.418 1.385.785 0 1.473-.413 1.426-1.429-.046-1.017-.721-1.797-1.506-1.797Zm-3.703"
    " 4.013c-.974 0-1.907.048-2.77.135-.147.015-.241.168-.183.305.483 1.154 1.622 1.964 2.953 1.964 1.33 0"
    " 2.47-.81 2.953-1.964.057-.137-.037-.29-.184-.305-.863-.087-1.795-.135-2.769-.135Z"
)

_FACEBOOK_PATH = (
    "M9.101 23.691v-7.98H6.627v-3.667h2.474v-1.58c0-4.085 1.848-5.978 5.858-5.978.401 0 .955.042 1.468.103a8.68"
    " 8.68 0 0 1 1.141.195v3.325a8.623 8.623 0 0 0-.653-.036 26.805 26.805 0 0 0-.733-.009c-.707 0-1.259.096-1.675"
    " .309a1.686 1.686 0 0 0-.679.622c-.258.42-.374.995-.374 1.752v1.297h3.919l-.386 2.103-.287 1.564h-3.246v8.245"
    "C19.396 23.238 24 18.179 24 12.044c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.628 3.874 10.35 9.101 11.647Z"
)

# The real X (Twitter) brand mark — lucide's "x" icon is just a plain close/
# cross glyph, not the actual logo (see the module docstring's Simple Icons
# note for github/reddit/facebook, same source here).
_X_PATH = (
    "M14.234 10.162 22.977 0h-2.072l-7.591 8.824L7.251 0H.258l9.168 13.343L.258 24H2.33l8.016-9.318L16.749 24h6.993"
    "zm-2.837 3.299-.929-1.329L3.076 1.56h3.182l5.965 8.532.929 1.329 7.754 11.09h-3.182z"
)


def _brand_svg_icon(path: str, size: int) -> rx.Component:
    return rx.el.svg(
        rx.el.path(d=path),
        width=str(size),
        height=str(size),
        view_box="0 0 24 24",
        fill="var(--gray-11)",
    )


def _github_icon(size: int) -> rx.Component:
    # Same Simple Icons brand-mark path footer.py uses — lucide has dropped
    # every brand icon except "x" (see that file's own note).
    return _brand_svg_icon(_BRAND_ICON_PATHS["github"], size)


def _social_icon(platform: rx.Var[str]) -> rx.Component:
    # coin["social_links_primary"/"_extra"] (see CoinState._build_row) carry
    # a plain "platform" string per entry rather than a pre-built icon
    # component (Vars can't hold components) — rx.match picks the right
    # brand mark/lucide icon for whichever platform string a given entry is.
    return rx.match(
        platform,
        ("twitter", _brand_svg_icon(_X_PATH, 12)),
        ("github", _github_icon(12)),
        ("telegram", rx.icon("send", size=12)),
        ("reddit", _brand_svg_icon(_REDDIT_PATH, 12)),
        ("facebook", _brand_svg_icon(_FACEBOOK_PATH, 12)),
        rx.icon("link", size=12),
    )


def _dropdown_trigger() -> rx.Component:
    # Small chevron-down circle opening a popover — shared trigger look for
    # both the Contract row's "+N other chains" and the Socials row's
    # "+N more" overflow, so they read as the same interaction pattern.
    return _icon_circle(rx.icon("chevron-down", size=12))


def _links_section(coin: dict) -> rx.Component:
    # Website/Whitepaper/Socials/Contract/Explorers are all real links now,
    # sourced from CMC's /v2/info `urls` object (see MarketDataService.
    # _extract_urls) — every social platform CMC actually returns for that
    # field (twitter, source_code/github, chat/telegram, reddit, facebook),
    # each row/icon only rendering when that coin declared it, rather than
    # showing a dead placeholder link.
    return rx.vstack(
        rx.cond(
            coin["has_website"],
            _link_row(
                "Website",
                _link_pill(
                    rx.icon("globe", size=11),
                    rx.text("Website", size="1", weight="medium"),
                    href=coin["website_url"],
                ),
            ),
        ),
        rx.cond(
            coin["has_whitepaper"],
            _link_row(
                "Whitepaper",
                _link_pill(
                    rx.icon("file-text", size=11),
                    rx.text("Whitepaper", size="1", weight="medium"),
                    rx.icon("external-link", size=9),
                    href=coin["whitepaper_url"],
                ),
            ),
        ),
        rx.cond(
            coin["has_twitter"]
            | coin["has_telegram"]
            | coin["has_source_code"]
            | coin["has_reddit"]
            | coin["has_facebook"],
            _link_row(
                "Socials",
                rx.foreach(
                    coin["social_links_primary"].to(list[dict]),
                    lambda item: _icon_circle(_social_icon(item["platform"]), href=item["url"]),
                ),
                # Only the coins with more than 3 declared socials ever get
                # a dropdown — same "main ones inline, rest tucked away"
                # pattern as the Contract row's other-chains popover below.
                rx.cond(
                    coin["has_extra_socials"],
                    rx.popover.root(
                        rx.popover.trigger(_dropdown_trigger()),
                        rx.popover.content(
                            rx.vstack(
                                rx.foreach(
                                    coin["social_links_extra"].to(list[dict]),
                                    lambda item: _icon_circle(_social_icon(item["platform"]), href=item["url"]),
                                ),
                                spacing="2",
                            ),
                            size="1",
                        ),
                    ),
                ),
            ),
        ),
        rx.cond(
            coin["has_contract"],
            _link_row(
                "Contract",
                _link_pill(
                    rx.text(coin["main_chain"], size="1", color_scheme="gray"),
                    rx.hstack(
                        rx.text(coin["contract_address_display"], size="1", weight="medium"),
                        rx.icon("copy", size=10),
                        spacing="1",
                        align="center",
                    ),
                    stacked=True,
                    # Copies the full address, not the truncated display
                    # text — rx.set_clipboard is a browser-side special
                    # event, no backend round-trip needed for it — chained
                    # with show_copied_toast, which drives the centered
                    # "Copied" popup (see coin_detail_page()).
                    on_click=[rx.set_clipboard(coin["contract_address"]), CoinState.show_copied_toast],
                ),
                # A coin bridged/wrapped onto other chains besides its main
                # one shows those in a dropdown instead of a wall of pills —
                # each one copyable the same way as the main contract above.
                rx.cond(
                    coin["has_other_chain_contracts"],
                    rx.popover.root(
                        rx.popover.trigger(_dropdown_trigger()),
                        rx.popover.content(
                            rx.vstack(
                                rx.foreach(
                                    coin["other_chain_contracts"].to(list[dict]),
                                    lambda c: _link_pill(
                                        rx.text(c["platform_name"], size="1", color_scheme="gray"),
                                        rx.text(c["contract_address_display"], size="1", weight="medium"),
                                        rx.icon("copy", size=10),
                                        # Not stacked (unlike the main Contract pill above) — the
                                        # narrow-300px-column overlap that stacking fixed there
                                        # doesn't apply inside this popover, which has plenty of
                                        # its own width, so a single row reads cleaner here.
                                        on_click=[
                                            rx.set_clipboard(c["contract_address"]),
                                            CoinState.show_copied_toast,
                                        ],
                                    ),
                                ),
                                spacing="2",
                                align="start",
                            ),
                            size="1",
                        ),
                    ),
                ),
            ),
        ),
        rx.cond(
            coin["has_explorer"],
            _link_row(
                "Explorers",
                _link_pill(
                    rx.icon("compass", size=11),
                    rx.text("Explorer", size="1", weight="medium"),
                    rx.icon("external-link", size=9),
                    href=coin["explorer_url"],
                ),
            ),
        ),
        spacing="3",
        width="100%",
        align="start",
    )


def _tag_pill(text: rx.Var[str] | str) -> rx.Component:
    return rx.badge(text, variant="surface", color_scheme="gray", size="2", white_space="nowrap")


def _real_tag_group(label: str, tags: rx.Var, suffix: str = "") -> rx.Component:
    # coin["narrative_list"]/["platform_list"] come off a plain `dict`-typed
    # selected_coin var, so Reflex sees them as Any — .to(list[str]) tells
    # rx.foreach the concrete type it needs to iterate.
    return rx.vstack(
        rx.text(label, size="2", color_scheme="gray"),
        rx.hstack(
            rx.foreach(tags.to(list[str]), lambda t: _tag_pill(t + suffix if suffix else t)),
            spacing="2",
            wrap="wrap",
        ),
        spacing="2",
        width="100%",
        align="start",
    )


def _dummy_tag_group(label: str, tags: list[str]) -> rx.Component:
    return rx.vstack(
        rx.text(label, size="2", color_scheme="gray"),
        rx.hstack(*[_tag_pill(t) for t in tags], spacing="2", wrap="wrap"),
        spacing="2",
        width="100%",
        align="start",
    )


def _tags_section(coin: dict) -> rx.Component:
    # Category and Platform come straight from the real, dynamically-synced
    # CMC categories/contracts data (same source as the homepage's narrative/
    # chain pills) — Industry and Self-Reported Tags have no equivalent field
    # in what we sync, so those two stay dummy placeholders.
    return rx.vstack(
        _real_tag_group("Category", coin["narrative_list"]),
        _dummy_tag_group("Industry", _DUMMY_INDUSTRY_TAGS),
        _real_tag_group("Platform", coin["platform_list"], suffix=" Ecosystem"),
        _dummy_tag_group("Self-Reported Tags", _DUMMY_SELF_REPORTED_TAGS),
        spacing="4",
        width="100%",
        align="start",
    )


def _stat_row(label: str, value: rx.Var | str) -> rx.Component:
    return rx.hstack(
        rx.text(label, size="1", color_scheme="gray"),
        rx.spacer(),
        # text_align="right" — a long value (e.g. a supply figure with its
        # ticker suffix) wraps onto a second line in this narrow column, and
        # without an explicit alignment the shorter wrapped line centered
        # itself instead of lining up against the row's own right edge.
        rx.text(value, size="2", weight="medium", text_align="right"),
        width="100%",
        justify="between",
    )


def _info_column() -> rx.Component:
    coin = CoinState.selected_coin
    return rx.vstack(
        rx.hstack(
            rx.image(src=coin["icon_url"], width="40px", height="40px", border_radius="50%"),
            rx.vstack(
                # Smaller than the default size="5" — long names (e.g.
                # "Artificial Superintelligence Alliance") otherwise wrap
                # awkwardly next to the fixed 40px icon.
                rx.heading(coin["name"], size="4"),
                rx.hstack(
                    rx.text("$", coin["symbol"], color_scheme="gray", size="3"),
                    rx.badge("#", coin["cmc_rank"], color_scheme="gray", variant="surface", size="1"),
                    spacing="2",
                    align="center",
                ),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            rx.icon("star", size=18, color="var(--gray-9)"),
            rx.icon("share-2", size=18, color="var(--gray-9)"),
            spacing="3",
            align="center",
            width="100%",
        ),
        rx.hstack(
            rx.text(coin["price_display"], size="8", weight="bold"),
            rx.text(coin["change_24h_display"], " (24h)", size="3", weight="bold", color=coin["change_24h_color"]),
            align="baseline",
            spacing="2",
            wrap="wrap",
        ),
        rx.hstack(
            rx.badge("Spot", color_scheme="gray", variant="solid", size="2"),
            rx.badge("Derivatives", color_scheme="gray", variant="surface", size="2"),
            spacing="2",
        ),
        rx.box(
            rx.vstack(
                _stat_row("Market cap", coin["market_cap_display"]),
                _stat_row("Unlocked Mkt Cap", coin["market_cap_display"]),
                _stat_row("Volume (24h)", coin["volume_display"]),
                _stat_row("Vol/Mkt Cap (24h)", coin["vol_mkt_cap_display"]),
                _stat_row("FDV", coin["fdv_display"]),
                # No Basic-tier CMC equivalent for these two: Liquidity Score
                # is a paid-tier metric, holder counts need a separate
                # blockchain-explorer API — stay dummy "—" placeholders.
                _stat_row("Liq/Mkt Cap", "—"),
                _stat_row("Total supply", coin["total_supply_display"]),
                _stat_row("Max supply", coin["max_supply_display"]),
                _stat_row("Circulating supply", coin["circulating_supply_display"]),
                _stat_row("Holders", "—"),
                spacing="3",
                width="100%",
            ),
            padding="1em",
            border_radius="10px",
            background="var(--gray-a2)",
            width="100%",
        ),
        rx.vstack(
            rx.hstack(
                rx.text("Profile Score", size="1", color_scheme="gray"),
                rx.spacer(),
                rx.text("57%", size="1", weight="medium"),
                width="100%",
            ),
            rx.box(
                rx.box(width="57%", height="100%", background="var(--amber-9)", border_radius="9999px"),
                width="100%",
                height="6px",
                background="var(--gray-a4)",
                border_radius="9999px",
            ),
            spacing="1",
            width="100%",
        ),
        rx.divider(),
        _links_section(coin),
        rx.divider(),
        _tags_section(coin),
        spacing="4",
        width="100%",
        align="start",
    )


# Its own fixed, independent height (not derived from matching whatever the
# info/sentiment columns' content happens to be) — a shared constant so the
# side columns below can cap themselves to the same value and scroll their
# own overflow instead of stretching the whole row to match a long column.
_CHART_HEIGHTS = ["420px", "480px", "520px", "560px", "600px"]


def _x_post_card(post: dict) -> rx.Component:
    # Real post text + (when the scraper found one) an image, straight from
    # SocialService's cached_tweets — replaces the old X "Embedded Timeline"
    # widget, whose data backend (syndication.twitter.com) turned out to
    # rate-limit unpredictably regardless of traffic, silently collapsing to
    # an empty box with no error. These are plain data (already normalized
    # server-side, see app/services/social_service.py's _normalize), so
    # unlike that sealed widget iframe, they render as ordinary cards that
    # can use the same horizontal-scroll-with-arrows mechanics as the
    # alerts/news sliders elsewhere on this page (assets/chain_pills.js).
    return rx.link(
        rx.vstack(
            rx.text(post["text"], size="2", style={"white-space": "pre-wrap"}),
            rx.cond(
                post["has_image"],
                rx.image(
                    src=post["image_url"],
                    width="100%",
                    height="140px",
                    object_fit="cover",
                    border_radius="8px",
                    margin_top="0.5em",
                ),
            ),
            rx.spacer(),
            rx.hstack(
                rx.hstack(rx.icon("heart", size=13), rx.text(post["likes"], size="1"), spacing="1", align="center"),
                rx.hstack(
                    rx.icon("message-circle", size=13), rx.text(post["replies"], size="1"), spacing="1", align="center"
                ),
                rx.hstack(
                    rx.icon("repeat-2", size=13), rx.text(post["retweets"], size="1"), spacing="1", align="center"
                ),
                spacing="4",
                margin_top="0.6em",
                color_scheme="gray",
            ),
            align_items="stretch",
            spacing="2",
            height="100%",
        ),
        href=post["url"],
        is_external=True,
        underline="none",
        color="inherit",
        padding="0.85em",
        border_radius="10px",
        background="var(--gray-a2)",
        width=["240px", "260px", "300px", "320px", "320px"],
        flex_shrink="0",
        height="220px",
    )


def _x_slider_arrow_fix_script() -> rx.Component:
    # Shared by both _x_posts_slider and _x_fallback_slider below — both
    # mount asynchronously (real cards swap in once CoinState.
    # refresh_social_posts's background fetch completes; the fallback swaps
    # in immediately but still after the surrounding page's own async
    # pieces), unlike the news/alerts sliders' static dummy data, which is
    # already present in the DOM by the time chain_pills.js's
    # MutationObserver runs its first scan. Confirmed live that other
    # mutations elsewhere on the page keep firing around this same moment
    # (the chart iframe loading, the targeted-news list rendering, ...), and
    # whichever one happens to land last decides the arrows' final
    # visibility based on chain_pills.js's shared, delegated listener —
    # sometimes with stale (mid-reconciliation, near-zero) measurements.
    # Rather than race that shared listener's timing, this computes and
    # sets the correct visibility directly against this specific track,
    # polling briefly until the numbers stop changing across two
    # consecutive checks (i.e. layout has genuinely settled), so it's
    # correct regardless of what else the page is doing.
    return rx.script(
        "(function(){"
        "var lastKey=null, stableCount=0;"
        "var iv=setInterval(function(){"
        "var t=document.querySelector('.x-posts-slider-track');"
        "if(!t){return;}"
        "var wrap=t.closest('.x-posts-slider-wrap');"
        "var leftBtn=wrap && wrap.querySelector('.x-posts-scroll-left');"
        "var rightBtn=wrap && wrap.querySelector('.x-posts-scroll-right');"
        "if(!leftBtn||!rightBtn){return;}"
        "var key=t.scrollLeft+':'+t.clientWidth+':'+t.scrollWidth;"
        "if(key===lastKey){"
        "stableCount++;"
        "}else{"
        "stableCount=0; lastKey=key;"
        "}"
        "var atStart=t.scrollLeft<=1;"
        "var atEnd=t.scrollLeft+t.clientWidth>=t.scrollWidth-1;"
        "leftBtn.style.display=atStart?'none':'flex';"
        "rightBtn.style.display=atEnd?'none':'flex';"
        "if(stableCount>=2){clearInterval(iv);}"
        "}, 200);"
        "setTimeout(function(){clearInterval(iv);}, 3000);"
        "})();"
    )


def _x_posts_slider(coin: dict) -> rx.Component:
    # Same draggable/arrow-scrollable slider mechanics as the news/alerts
    # sliders (assets/chain_pills.js — its selectors include these
    # x-posts-* class names too), just real X-post cards instead.
    return rx.box(
        rx.box(rx.icon("chevron-left", size=14), class_name="x-posts-scroll-btn x-posts-scroll-left"),
        rx.box(
            rx.foreach(coin["cached_tweets"].to(list[dict]), _x_post_card),
            class_name="x-posts-slider-track",
        ),
        rx.box(rx.icon("chevron-right", size=14), class_name="x-posts-scroll-btn x-posts-scroll-right"),
        _x_slider_arrow_fix_script(),
        class_name="x-posts-slider-wrap",
    )


def _x_skeleton_card(url: rx.Var[str]) -> rx.Component:
    # A single skeleton placeholder — same size/shape as a real _x_post_card
    # so the fallback slider (see _x_fallback_slider) reads as "posts are
    # coming" rather than fabricating fake tweet text/engagement numbers,
    # which the rest of this page's actually-dummy sections (_post_card,
    # _targeted_news_card) are explicit, documented placeholders for but
    # this section isn't — X posts have a real backend (SocialService),
    # it's just not always available (see _x_timeline_section). Still
    # clickable straight through to the coin's real X profile.
    return rx.link(
        rx.vstack(
            rx.box(width="90%", height="12px", background="var(--gray-a5)", border_radius="4px"),
            rx.box(width="70%", height="12px", background="var(--gray-a5)", border_radius="4px"),
            rx.box(width="95%", height="12px", background="var(--gray-a5)", border_radius="4px"),
            rx.spacer(),
            rx.hstack(
                _brand_svg_icon(_X_PATH, 14),
                rx.text("View on X", size="1", color_scheme="gray"),
                spacing="1",
                align="center",
            ),
            align_items="stretch",
            spacing="2",
            height="100%",
        ),
        href=url,
        is_external=True,
        underline="none",
        color="inherit",
        padding="0.85em",
        border_radius="10px",
        background="var(--gray-a2)",
        width=["240px", "260px", "300px", "320px", "320px"],
        flex_shrink="0",
        height="220px",
    )


def _x_fallback_slider(coin: dict) -> rx.Component:
    # Shown while no cached tweets are available yet — either the on-demand
    # scraper fetch (CoinState.refresh_social_posts) hasn't completed for
    # this coin's first-ever view, the scraper API isn't configured
    # (settings.apify_api_token empty), or a real fetch attempt failed with
    # nothing already cached to fall back to. Same horizontal-scroll-with-
    # arrows shape as the real _x_posts_slider (10 cards, ~3.5 visible) per
    # explicit request, rather than a single plain link — each card still
    # links out to the coin's real X profile.
    return rx.box(
        rx.box(rx.icon("chevron-left", size=14), class_name="x-posts-scroll-btn x-posts-scroll-left"),
        rx.box(
            *[_x_skeleton_card(coin["twitter_url"]) for _ in range(10)],
            class_name="x-posts-slider-track",
        ),
        rx.box(rx.icon("chevron-right", size=14), class_name="x-posts-scroll-btn x-posts-scroll-right"),
        _x_slider_arrow_fix_script(),
        class_name="x-posts-slider-wrap",
    )


def _x_timeline_section() -> rx.Component:
    # Only rendered when this coin actually declared an X account (same
    # has_twitter flag _links_section uses).
    coin = CoinState.selected_coin
    return rx.cond(
        coin["has_twitter"],
        rx.vstack(
            rx.hstack(
                rx.heading(coin["name"], " on X", size="4"),
                rx.link(
                    rx.hstack(
                        rx.text("View More", size="2", weight="bold"),
                        rx.icon("arrow-right", size=14),
                        spacing="1",
                        align="center",
                    ),
                    href=coin["twitter_url"],
                    is_external=True,
                    underline="none",
                    # Same color_scheme="indigo" pattern as the "More News"/
                    # "See More" links elsewhere on this page.
                    color_scheme="indigo",
                ),
                width="100%",
                justify="between",
                align="center",
            ),
            rx.cond(coin["has_cached_tweets"], _x_posts_slider(coin), _x_fallback_slider(coin)),
            spacing="3",
            width="100%",
            align="center",
        ),
    )


def _about_section() -> rx.Component:
    # Real, free-text project description straight from CMC's /v2/info
    # payload (see app/services/market_data_service.py::_upsert_contracts —
    # same response website_url/whitepaper_url/etc. already come from, so
    # this is free: no new API call, just one more field persisted from a
    # response already fetched). No collapse/expand toggle per explicit
    # request — always shown in full, unlike the reference design's
    # dropdown-style card.
    coin = CoinState.selected_coin
    return rx.cond(
        coin["has_description"],
        rx.vstack(
            rx.hstack(
                rx.heading("About ", coin["name"], size="4"),
                rx.icon("info", size=16, color="var(--gray-9)"),
                spacing="2",
                align="center",
            ),
            rx.box(
                rx.text(coin["description"], size="2", color_scheme="gray", style={"white-space": "pre-wrap"}),
                padding="1.25em",
                border_radius="10px",
                background="var(--gray-a2)",
                width="100%",
            ),
            spacing="3",
            width="100%",
            align="start",
        ),
    )


def _chart_column() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.heading(CoinState.selected_coin["name"], " Live Chart", size="4"),
            spacing="1",
            align="center",
            # width="100%" so this row spans the vstack instead of
            # shrink-wrapping — without it, the vstack's own align="center"
            # (needed to center the narrower, max-width-capped chart box
            # below) was also centering this heading instead of letting it
            # sit flush left.
            width="100%",
        ),
        rx.box(
            # This box has a genuinely definite height at every breakpoint
            # (a plain fixed value, not flex-derived), so rx.html's wrapping
            # div can safely take height="100%" against it and the iframe's
            # own inline height:100% then resolves correctly in turn.
            #
            # CoinState.tradingview_iframe_src_light/_dark are plain server-
            # cached vars, unaware of the client's (next-themes) color-mode
            # preference — rx.color_mode_cond is what's actually reactive to
            # that on the frontend, so it picks between the two here rather
            # than the state var trying to know the theme itself.
            rx.html(
                f'<iframe src="{rx.color_mode_cond(light=CoinState.tradingview_iframe_src_light, dark=CoinState.tradingview_iframe_src_dark)}" style="width:100%;height:100%;border:none;" allowtransparency="true" frameborder="0"></iframe>',
                width="100%",
                height="100%",
            ),
            width="100%",
            # Constrained instead of letting it stretch edge-to-edge of the
            # (often quite wide) flexible middle column — a plain 100%-width
            # chart looked stretched/oversized; this keeps it a contained,
            # nicely-proportioned rectangle, centered via the vstack's own
            # align="center" below.
            max_width="760px",
            height=_CHART_HEIGHTS,
            border_radius="10px",
            overflow="hidden",
            # Matches CoinState._tradingview_iframe_src's own theme-aware
            # backgroundColor/gridColor (black in dark mode, white in light
            # mode) — this is just the placeholder shown before the iframe
            # paints, so it should already look like the chart that's about
            # to load rather than always black.
            background=rx.color_mode_cond(light="#ffffff", dark="#000000"),
        ),
        _x_timeline_section(),
        _about_section(),
        spacing="3",
        width="100%",
        align="center",
    )


def _post_card(post: dict, index: int) -> rx.Component:
    is_positive = post["sentiment"] == "positive"
    return rx.vstack(
        rx.hstack(
            rx.image(
                # pravatar.cc serves a fixed, real-looking placeholder photo
                # per numeric seed (1-70) — deterministic per post index
                # rather than truly random, so it doesn't change on every
                # re-render/reload.
                src=f"https://i.pravatar.cc/64?img={(index % 70) + 1}",
                width="32px",
                height="32px",
                border_radius="50%",
                flex_shrink="0",
            ),
            rx.vstack(
                rx.hstack(
                    rx.text(post["author"], size="2", weight="bold"),
                    rx.text(post["handle"], size="1", color_scheme="gray"),
                    spacing="1",
                    align="center",
                ),
                rx.text(post["time"], size="1", color_scheme="gray"),
                spacing="0",
                align="start",
            ),
            rx.spacer(),
            # Green/red pulsing trending arrow reflecting this specific
            # post's dummy sentiment — same shine technique styles.css
            # already uses for extreme price moves, just green/red instead
            # of gold/red.
            rx.icon(
                "trending-up" if is_positive else "trending-down",
                size=16,
                color="#22c55e" if is_positive else "#ef4444",
                class_name="sentiment-positive-pulse" if is_positive else "sentiment-negative-pulse",
            ),
            spacing="2",
            align="center",
            width="100%",
        ),
        rx.text(
            post["body_before"],
            "$",
            CoinState.selected_coin["symbol"],
            post["body_after"],
            size="2",
            margin_top="0.4em",
        ),
        rx.hstack(
            rx.hstack(rx.icon("heart", size=13), rx.text(post["likes"], size="1"), spacing="1", align="center"),
            rx.hstack(rx.icon("message-circle", size=13), rx.text(post["comments"], size="1"), spacing="1", align="center"),
            rx.hstack(rx.icon("repeat-2", size=13), rx.text(post["reposts"], size="1"), spacing="1", align="center"),
            spacing="4",
            margin_top="0.5em",
            color_scheme="gray",
        ),
        padding="0.85em",
        border_radius="10px",
        background="var(--gray-a2)",
        width="100%",
        align_items="stretch",
    )


def _sentiment_column() -> rx.Component:
    return rx.vstack(
        rx.heading("Community", size="4"),
        rx.hstack(
            rx.heading("Social Insights", size="3"),
            rx.spacer(),
            rx.link(
                rx.hstack(rx.text("See More", size="2"), rx.icon("arrow-right", size=14), spacing="1", align="center"),
                href="#",
                underline="none",
                # Same color_scheme="indigo" pattern as news_feed.py's "More
                # News" link — a hardcoded color="white" here was unreadable
                # in light mode.
                color_scheme="indigo",
            ),
            width="100%",
            align="center",
        ),
        rx.hstack(
            rx.vstack(
                rx.text("24h Mindshare", size="1", color_scheme="gray"),
                # Exact count of sentiment posts analyzed (10 for this fixed
                # dummy dataset) — see _MINDSHARE_DISPLAY above.
                rx.text(_MINDSHARE_DISPLAY, size="5", weight="bold"),
                spacing="1",
                align="start",
            ),
            rx.vstack(
                rx.text("24h Sentiment", size="1", color_scheme="gray"),
                # Both sides of the split shown side by side — positive
                # share * 10 in green, negative share * 10 in red — rather
                # than only whichever side has the majority.
                rx.hstack(
                    rx.badge(_SENTIMENT_SCORE_DISPLAY, color_scheme=_SENTIMENT_COLOR, variant="solid", size="2"),
                    rx.badge(_NEGATIVE_SENTIMENT_SCORE_DISPLAY, color_scheme="red", variant="solid", size="2"),
                    spacing="2",
                ),
                spacing="1",
                align="start",
            ),
            justify="between",
            width="100%",
        ),
        rx.box(
            rx.vstack(
                *[_post_card(post, i) for i, post in enumerate(_DUMMY_POSTS)], spacing="3", width="100%"
            ),
            # Tall enough to show exactly 3.5 cards, with the sliced-off
            # half acting as a "there's more, scroll" cue — overflow_y=
            # "auto" + hide-scrollbar keeps it genuinely scrollable without
            # the scrollbar chrome (styles.css, same technique used
            # elsewhere on this page). 585px = 3.5 * a real card's measured
            # height (156.78px) + 3 * the vstack's own gap (12px, from
            # spacing="3") between them.
            height="585px",
            overflow_y="auto",
            # Explicit, not left to default "visible" — per the CSS Overflow
            # spec, a "visible" cross-axis value gets silently forced to
            # "auto" too once the other axis is non-visible (same quirk
            # documented in styles.css's .coin-table-scroll-fix), which was
            # showing an unwanted horizontal scrollbar whenever a card's
            # content ran even slightly wider than this box.
            overflow_x="hidden",
            class_name="hide-scrollbar",
            width="100%",
        ),
        spacing="4",
        width="100%",
        align="start",
    )


_NEWS_SOURCE_COLORS = {
    "Bloomberg": "blue",
    "Cointelegraph": "green",
    "Reuters": "orange",
    "CoinDesk": "purple",
}

# Same "$<SYMBOL>"-style dynamic mention as _DUMMY_POSTS, but each item here
# mentions either the coin's ticker OR its primary narrative (CMC's real,
# dynamically-synced category — see CoinState._build_row's primary_narrative)
# — "mention" picks which Var this item's headline is built around. 10 items,
# no duplicates, same fixed dataset reused on every coin's page (only the
# actual $<SYMBOL>/narrative text substituted per coin).
_TARGETED_NEWS = [
    {
        "source": "Bloomberg",
        "time": "20m ago",
        "mention": "ticker",
        "headline_before": "",
        "headline_after": " gains fresh institutional coverage after its latest roadmap update",
        "body": "Analysts note growing interest from allocators tracking the project's execution against its public milestones.",
    },
    {
        "source": "Cointelegraph",
        "time": "1h ago",
        "mention": "narrative",
        "headline_before": "",
        "headline_after": " narrative broadens as new protocols enter the race",
        "body": "Momentum in the space continues to build as builders ship competing implementations.",
    },
    {
        "source": "Reuters",
        "time": "2h ago",
        "mention": "ticker",
        "headline_before": "Exchange inflows for ",
        "headline_after": " tick higher amid renewed trading activity",
        "body": "Higher exchange balances often precede short-term volatility as traders reposition.",
    },
    {
        "source": "CoinDesk",
        "time": "3h ago",
        "mention": "ticker",
        "headline_before": "",
        "headline_after": " developer activity climbs on fresh GitHub commit data",
        "body": "Weekly commit counts suggest the core team is shipping at a faster cadence than last quarter.",
    },
    {
        "source": "Bloomberg",
        "time": "5h ago",
        "mention": "narrative",
        "headline_before": "Capital rotates back into ",
        "headline_after": " tokens as risk appetite improves",
        "body": "Traders point to the sector's recent underperformance as a reason for the renewed interest.",
    },
    {
        "source": "Cointelegraph",
        "time": "7h ago",
        "mention": "ticker",
        "headline_before": "",
        "headline_after": " community proposal targets improved incentive design",
        "body": "The governance forum discussion has drawn unusually high engagement from long-term holders.",
    },
    {
        "source": "Reuters",
        "time": "9h ago",
        "mention": "ticker",
        "headline_before": "Analysts flag ",
        "headline_after": " as a name to watch heading into next quarter",
        "body": "The commentary cites a mix of technical setup and upcoming catalysts as reasons for the call.",
    },
    {
        "source": "CoinDesk",
        "time": "12h ago",
        "mention": "narrative",
        "headline_before": "",
        "headline_after": " projects see renewed venture funding interest",
        "body": "Several early-stage rounds closed this week, signaling investor appetite hasn't cooled.",
    },
    {
        "source": "Bloomberg",
        "time": "16h ago",
        "mention": "ticker",
        "headline_before": "",
        "headline_after": " liquidity deepens across major trading venues",
        "body": "Tighter spreads and larger order-book depth typically make for smoother price discovery.",
    },
    {
        "source": "Cointelegraph",
        "time": "1d ago",
        "mention": "narrative",
        "headline_before": "Regulatory clarity could be a tailwind for ",
        "headline_after": " tokens",
        "body": "Industry participants say clearer rules would likely accelerate institutional participation.",
    },
]


def _targeted_news_card(item: dict) -> rx.Component:
    coin = CoinState.selected_coin
    # coin["symbol"]/["primary_narrative"] come off a plain `dict`-typed
    # selected_coin var, so Reflex sees them as Any — .to(str) is needed
    # before "+" concatenation works (same issue _real_tag_group hit).
    mention = (
        "$" + coin["symbol"].to(str) if item["mention"] == "ticker" else coin["primary_narrative"].to(str)
    )
    return rx.box(
        rx.hstack(
            rx.badge(item["source"], color_scheme=_NEWS_SOURCE_COLORS.get(item["source"], "gray"), size="1"),
            rx.spacer(),
            rx.text(item["time"], size="1", color_scheme="gray"),
            width="100%",
            align="center",
        ),
        rx.hstack(
            rx.badge(coin["symbol"], color_scheme="indigo", size="1"),
            rx.badge(coin["primary_narrative"], color_scheme="orange", size="1"),
            margin_top="0.5em",
            width="100%",
            direction="row-reverse",
            justify="end",
            wrap="wrap",
        ),
        rx.text(
            item["headline_before"], mention, item["headline_after"],
            weight="bold", size="2", margin_top="0.4em",
        ),
        rx.text(item["body"], size="1", color_scheme="gray", margin_top="0.3em"),
        padding="0.85em",
        border_radius="8px",
        background="var(--gray-a2)",
        width="100%",
    )


def _targeted_news_section() -> rx.Component:
    coin = CoinState.selected_coin
    return rx.vstack(
        rx.text("TARGETED NARRATIVE NEWS", size="1", color_scheme="gray", weight="bold"),
        rx.hstack(
            rx.heading(coin["name"], " News", size="5"),
            rx.link(
                rx.hstack(rx.text("More News", size="2", weight="bold"), rx.icon("arrow-right", size=14), spacing="1", align="center"),
                href="#",
                underline="none",
                # Same color_scheme="indigo" pattern as news_feed.py's own
                # "More News" link on the homepage.
                color_scheme="indigo",
            ),
            width="100%",
            justify="between",
            align="center",
            wrap="wrap",
        ),
        # Same fixed-height, 3.5-card scrollable box as the sentiment
        # column's _post_card list right above it (both now live in the same
        # sidebar column) — hide-scrollbar keeps it genuinely scrollable
        # without the scrollbar chrome (styles.css).
        rx.box(
            rx.vstack(
                *[_targeted_news_card(item) for item in _TARGETED_NEWS],
                spacing="3",
                width="100%",
            ),
            height="585px",
            overflow_y="auto",
            # See _sentiment_column's identical box for why this is explicit.
            overflow_x="hidden",
            class_name="hide-scrollbar",
            width="100%",
        ),
        spacing="3",
        width="100%",
        align_items="stretch",
    )


def _not_found() -> rx.Component:
    return rx.vstack(
        rx.heading("Coin not found", size="5"),
        rx.text("This coin isn't in our cached universe, or the sync hasn't finished loading yet.", color_scheme="gray"),
        rx.link(rx.text("← Back to all coins"), href="/", underline="always"),
        spacing="3",
        padding="3em",
        align="center",
        width="100%",
    )


def _copied_toast() -> rx.Component:
    # Centered, fixed-position popup confirming the Contract-address copy —
    # driven by CoinState.contract_copied, which show_copied_toast flips
    # true then back to false after 3s. Lives once per coin_detail_page(),
    # so it applies on every coin's page automatically.
    return rx.cond(
        CoinState.contract_copied,
        rx.box(
            rx.hstack(
                rx.icon("check", size=16),
                rx.text("Contract address copied to clipboard", size="2", weight="bold"),
                spacing="2",
                align="center",
            ),
            position="fixed",
            top="50%",
            left="50%",
            transform="translate(-50%, -50%)",
            background="rgba(0, 0, 0, 0.85)",
            color="white",
            padding="0.9em 1.4em",
            border_radius="10px",
            z_index="9999",
        ),
    )


def coin_detail_page() -> rx.Component:
    # The row no longer forces the page into one fixed viewport height (that
    # approach — coin_detail()'s root at a hard height="100vh" plus
    # min_height="0" everywhere down the chain — made the *whole page*
    # un-scrollable past one screen, clipping content instead of just
    # bounding the chart). Now the page is free to grow to whatever height
    # its tallest column naturally needs, like a normal web page.
    #
    # The chart keeps its own fixed height (_CHART_HEIGHTS) independent of
    # its siblings — align="start" (not "stretch") stops the row from
    # matching every column's height to the tallest one, which is what
    # previously ballooned the chart to 1500px+ once the info column grew a
    # long links/tags section. The two side columns are height="max-content"
    # — natural, uncapped, no internal scroll — so only the chart has a
    # fixed height; a max_height matching the chart was tried here too, but
    # that just re-imposed the same "everything capped to one height" look
    # the align="start" change was meant to get away from.
    return rx.fragment(
        _copied_toast(),
        rx.cond(
            CoinState.is_loading,
            rx.center(rx.spinner(size="3"), padding="4em"),
            rx.cond(
                CoinState.selected_coin_found,
                rx.box(
                    rx.vstack(
                        rx.hstack(
                            rx.box(
                                _info_column(),
                                width=["100%", "100%", "100%", "300px", "300px"],
                                flex_shrink="0",
                                height="max-content",
                            ),
                            rx.box(
                                _chart_column(),
                                flex="1",
                                min_width="0",
                            ),
                            rx.box(
                                rx.vstack(
                                    _sentiment_column(),
                                    _targeted_news_section(),
                                    spacing="6",
                                    width="100%",
                                ),
                                width=["100%", "100%", "100%", "300px", "300px"],
                                flex_shrink="0",
                                height="max-content",
                                # Both children above are fixed-width to
                                # this box already, but this guards against
                                # any stray horizontal bleed now that the
                                # news cards live in this narrower sidebar
                                # column instead of the page's full width.
                                overflow="hidden",
                            ),
                            direction=rx.breakpoints(initial="column", lg="row"),
                            align="start",
                            width="100%",
                            style={"gap": "25px"},
                        ),
                        spacing="6",
                        width="100%",
                    ),
                    padding=["1em", "1em", "1.5em", "2em", "2em"],
                    width="100%",
                ),
                _not_found(),
            ),
        ),
    )
