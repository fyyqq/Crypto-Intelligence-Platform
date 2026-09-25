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


# AI-provider brand marks for the business-summary attribution badge (see
# _business_summary_section) — Simple Icons paths, same source/verification
# approach as _REDDIT_PATH/_FACEBOOK_PATH/_X_PATH above. Only the providers
# actually reachable through this project's free-tier OpenRouter account
# need to be exact (see CoinState._PROVIDER_DISPLAY_NAMES) — a handful of
# other likely ones are included too so the badge already has a real logo
# ready if the configured model ever changes, rather than only ever
# showing the generic fallback.
_AI_PROVIDER_PATHS = {
    "nvidia": (
        "M8.948 8.798v-1.43a6.7 6.7 0 0 1 .424-.018c3.922-.124 6.493 3.374 6.493 3.374s-2.774 3.851-5.75 3.851c-.398"
        " 0-.787-.062-1.158-.185v-4.346c1.528.185 1.837.857 2.747 2.385l2.04-1.714s-1.492-1.952-4-1.952a6.016 6.016"
        " 0 0 0-.796.035m0-4.735v2.138l.424-.027c5.45-.185 9.01 4.47 9.01 4.47s-4.08 4.964-8.33 4.964c-.37"
        " 0-.733-.035-1.095-.097v1.325c.3.035.61.062.91.062 3.957 0 6.82-2.023 9.593-4.408.459.371 2.34 1.263 2.73"
        " 1.652-2.633 2.208-8.772 3.984-12.253 3.984-.335 0-.653-.018-.971-.053v1.864H24V4.063zm0 10.326v1.131c-3.657"
        "-.654-4.673-4.46-4.673-4.46s1.758-1.944 4.673-2.262v1.237H8.94c-1.528-.186-2.73 1.245-2.73"
        " 1.245s.68 2.412 2.739 3.11M2.456 10.9s2.164-3.197 6.5-3.533V6.201C4.153 6.59 0 10.653 0 10.653s2.35 6.802"
        " 8.948 7.42v-1.237c-4.84-.6-6.492-5.936-6.492-5.936z"
    ),
    "openai": (
        "M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807"
        " 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051"
        " 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894"
        " 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l"
        ".1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a"
        "4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a"
        ".7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0"
        " 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144"
        " 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963"
        " 3.8558L13.1038 8.364 15.1192 7.2a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765"
        " 8.1042v-5.6772a.79.79 0 0 0-.407-.667zm2.0107-3.0231l-.142-.0852-4.7735-2.7818a.7759.7759 0 0"
        " 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802"
        " 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.4537l"
        "-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813zm1.0976-2.3654l2.602-1.4998 2.6069 1.4998v2.9994l"
        "-2.5974 1.4997-2.6067-1.4997Z"
    ),
    "anthropic": (
        "M17.3041 3.541h-3.6718l6.696 16.918H24Zm-10.6082 0L0 20.459h3.7442l1.3693-3.5527h7.0052l1.3693 3.5528h3.7442"
        "L10.5363 3.5409Zm-.3712 10.2232 2.2914-5.9456 2.2914 5.9456Z"
    ),
    "google": (
        "M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827"
        " 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0"
        " 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213"
        " 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z"
    ),
    "meta-llama": (
        "M6.915 4.03c-1.968 0-3.683 1.28-4.871 3.113C.704 9.208 0 11.883 0 14.449c0 .706.07 1.369.21 1.973a6.624"
        " 6.624 0 0 0 .265.86 5.297 5.297 0 0 0 .371.761c.696 1.159 1.818 1.927 3.593 1.927 1.497 0 2.633-.671"
        " 3.965-2.444.76-1.012 1.144-1.626 2.663-4.32l.756-1.339.186-.325c.061.1.121.196.183.3l2.152 3.595c.724"
        " 1.21 1.665 2.556 2.47 3.314 1.046.987 1.992 1.22 3.06 1.22 1.075 0 1.876-.355 2.455-.843a3.743 3.743 0 0"
        " 0 .81-.973c.542-.939.861-2.127.861-3.745 0-2.72-.681-5.357-2.084-7.45-1.282-1.912-2.957-2.93-4.716-2.93"
        "-1.047 0-2.088.467-3.053 1.308-.652.57-1.257 1.29-1.82 2.05-.69-.875-1.335-1.547-1.958-2.056"
        "-1.182-.966-2.315-1.303-3.454-1.303zm10.16 2.053c1.147 0 2.188.758 2.992 1.999 1.132 1.748 1.647 4.195"
        " 1.647 6.4 0 1.548-.368 2.9-1.839 2.9-.58 0-1.027-.23-1.664-1.004-.496-.601-1.343-1.878-2.832-4.358l"
        "-.617-1.028a44.908 44.908 0 0 0-1.255-1.98c.07-.109.141-.224.211-.327 1.12-1.667 2.118-2.602"
        " 3.358-2.602zm-10.201.553c1.265 0 2.058.791 2.675 1.446.307.327.737.871 1.234 1.579l-1.02 1.566c-.757"
        " 1.163-1.882 3.017-2.837 4.338-1.191 1.649-1.81 1.817-2.486 1.817-.524 0-1.038-.237-1.383-.794-.263"
        "-.426-.464-1.13-.464-2.046 0-2.221.63-4.535 1.66-6.088.454-.687.964-1.226 1.533-1.533a2.264 2.264 0 0 1"
        " 1.088-.285z"
    ),
    "deepseek": (
        "M23.748 4.651c-.254-.124-.364.113-.512.233-.051.04-.094.09-.137.137-.372.397-.806.657-1.373.626-.829"
        "-.046-1.537.214-2.163.848-.133-.782-.575-1.248-1.247-1.548-.352-.155-.708-.311-.955-.65-.172-.24-.219"
        "-.509-.305-.774-.055-.16-.11-.323-.293-.35-.2-.031-.278.136-.356.276-.313.572-.434 1.202-.422 1.84.027"
        " 1.436.633 2.58 1.838 3.393.137.094.172.187.129.323-.082.28-.18.553-.266.833-.055.179-.137.218-.328.14a5.5"
        " 5.5 0 0 1-1.737-1.179c-.857-.828-1.631-1.743-2.597-2.46a12 12 0 0 0-.689-.47c-.985-.957.13-1.743"
        ".387-1.836.27-.098.094-.433-.778-.428-.872.003-1.67.295-2.687.685a3 3 0 0 1-.465.136 9.6 9.6 0 0 0-2.883"
        "-.101c-1.885.21-3.39 1.1-4.497 2.622C.082 8.776-.231 10.854.152 13.02c.403 2.284 1.568 4.175 3.36 5.653"
        " 1.857 1.533 3.997 2.284 6.438 2.14 1.482-.085 3.132-.284 4.994-1.86.47.234.962.328 1.78.398.629.058"
        " 1.235-.031 1.705-.129.735-.155.684-.836.418-.961-2.155-1.004-1.682-.595-2.112-.926 1.095-1.295 2.768"
        "-3.598 3.284-6.733.05-.346.115-.834.108-1.114-.004-.171.035-.238.23-.257a4.2 4.2 0 0 0 1.545-.475c1.397"
        "-.763 1.96-2.016 2.093-3.517.02-.23-.004-.467-.247-.588M11.58 18.168c-2.088-1.642-3.101-2.183-3.52-2.16"
        "-.39.024-.32.472-.234.763.09.288.207.487.371.74.114.167.192.416-.113.603-.673.416-1.842-.14-1.897-.168"
        "-1.361-.801-2.5-1.86-3.301-3.306-.775-1.393-1.225-2.888-1.299-4.482-.02-.385.094-.522.477-.592a4.7 4.7 0"
        " 0 1 1.53-.038c2.131.311 3.946 1.264 5.467 2.774.868.86 1.525 1.887 2.202 2.89.72 1.066 1.494 2.082 2.48"
        " 2.915.348.291.626.513.892.677-.802.09-2.14.109-3.055-.615zm1.001-6.44a.306.306 0 0 1 .415-.287.3.3 0 0 1"
        " .113.074.3.3 0 0 1 .086.214c0 .17-.136.307-.308.307a.303.303 0 0 1-.306-.307m3.11 1.596c-.2.081-.4.151"
        "-.591.16a1.25 1.25 0 0 1-.798-.254c-.274-.23-.47-.358-.551-.758a1.7 1.7 0 0 1 .015-.588c.07-.327-.007"
        "-.537-.238-.727-.188-.156-.426-.199-.689-.199a.6.6 0 0 1-.254-.078.253.253 0 0 1-.114-.358 1 1 0 0 1 .192"
        "-.21c.356-.202.767-.136 1.146.016.352.144.618.408 1.001.782.392.451.462.576.685.915.176.264.336.536.446"
        ".848.066.194-.02.353-.25.45"
    ),
    "qwen": (
        "M23.919 14.545 20.817 9.17l1.47-2.544a.56.56 0 0 0 0-.566l-1.633-2.83a.57.57 0 0 0-.49-.283h-6.207L12.487"
        ".402a.57.57 0 0 0-.49-.284H8.732a.56.56 0 0 0-.49.284L5.139 5.775h-2.94a.56.56 0 0 0-.49.284L.077"
        " 8.887a.56.56 0 0 0 0 .567L3.18 14.83l-1.47 2.545a.56.56 0 0 0 0 .566l1.634 2.83a.57.57 0 0 0 .49.283h6.205"
        "l1.47 2.545a.57.57 0 0 0 .49.284h3.266a.57.57 0 0 0 .49-.284l3.104-5.375h2.94a.57.57 0 0 0 .49-.283l1.634"
        "-2.828a.55.55 0 0 0-.004-.568M8.733.686l1.634 2.828-1.634 2.828H21.8L20.164 9.17H7.425L5.63"
        " 6.06Zm1.306 19.801-6.205-.002 1.634-2.83h3.265L2.201 6.344h3.267q3.182 5.517 6.367 11.032zm10.124-5.66L18.53"
        " 12l-6.532 11.315-1.634-2.83c2.129-3.673 4.25-7.351 6.373-11.028h3.592l3.102 5.374z"
    ),
    "mistralai": (
        "M17.143 3.429v3.428h-3.429v3.429h-3.428V6.857H6.857V3.43H3.43v13.714H0v3.428h10.286v-3.428H6.857v-3.429h3.429"
        "v3.429h3.429v-3.429h3.428v3.429h-3.428v3.428H24v-3.428h-3.43V3.429z"
    ),
}


def _ai_provider_icon(provider: rx.Var[str], size: int = 13) -> rx.Component:
    # coin["business_summary_model_badge"]["provider"] (see CoinState.
    # _format_model_badge) carries the raw OpenRouter provider slug —
    # rx.match picks the matching brand mark, falling back to a generic
    # "bot" icon for any provider not in _AI_PROVIDER_PATHS (keeps the badge
    # working even if the configured model's provider ever changes to one
    # without a logo mapped here yet).
    return rx.match(
        provider,
        *[(key, _brand_svg_icon(path, size)) for key, path in _AI_PROVIDER_PATHS.items()],
        rx.icon("bot", size=size),
    )


def _dropdown_trigger() -> rx.Component:
    # Small chevron-down circle opening a popover — shared trigger look for
    # both the Contract row's "+N other chains" and the Socials row's
    # "+N more" overflow, so they read as the same interaction pattern.
    return _icon_circle(rx.icon("chevron-down", size=12))


# 10.5 rows of the Contract dropdown's chain pills (~34px each incl. its
# spacing="2" gap, measured live) — tall enough that the visibly cut-off
# 11th row reads as "more below, scroll" rather than looking like the list
# just ends there.
_CHAIN_DROPDOWN_HEIGHT = "357px"


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
                            # Fixed height + its own scroll — a coin with many
                            # declared socials was rendering a popover taller
                            # than the viewport with no way to scroll it,
                            # spilling off/overlapping the page underneath.
                            # Sized (see the Contract dropdown below, which
                            # shares this exact value) to show ~10.5 rows —
                            # tall enough that the cut-off last row is an
                            # obvious "more below, scroll" cue rather than
                            # looking like the end of the list — with a
                            # visible (not OS-auto-hiding) scrollbar so
                            # that cue doesn't depend on noticing the
                            # clipped row alone.
                            max_height=_CHAIN_DROPDOWN_HEIGHT,
                            overflow_y="auto",
                            class_name="visible-scrollbar",
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
                            # Same fixed-height + scroll fix as the Socials
                            # dropdown above — a coin bridged/wrapped across
                            # many chains was rendering a popover taller than
                            # the viewport with no scroll, overlapping the
                            # page underneath instead of scrolling its own
                            # list. ~10.5 pills tall with a visible
                            # scrollbar (see _CHAIN_DROPDOWN_HEIGHT).
                            max_height=_CHAIN_DROPDOWN_HEIGHT,
                            overflow_y="auto",
                            class_name="visible-scrollbar",
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
                    # Same color_scheme="indigo" pattern as the "View More"/
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


def _render_highlight_token(token: dict) -> rx.Component:
    # Plain runs render as-is; highlighted runs (see CoinState._tokenize_
    # highlights — investor-relevant terms/figures like "Layer 2" or a
    # concrete $/% figure) get a colored underline rather than a background
    # highlight, matching the reference style (bold text, colored underline
    # beneath) rather than a highlighter-pen block behind the word.
    return rx.cond(
        token["highlight"],
        rx.el.span(
            token["text"],
            style={
                "text-decoration": "underline",
                "text-decoration-color": token["color"],
                "text-decoration-thickness": "2.5px",
                "text-underline-offset": "3px",
                "font-weight": "600",
            },
        ),
        rx.el.span(token["text"]),
    )


def _highlighted_paragraph(tokens: rx.Var) -> rx.Component:
    return rx.text(
        rx.foreach(tokens.to(list[dict]), _render_highlight_token),
        size="2",
        color_scheme="gray",
        style={"white-space": "pre-wrap"},
    )


# Tall enough to show ~3.5 paragraphs of a typical About description at
# this box's width/font-size (measured live against Ethereum's real
# description) before clipping — the same "3.5 visible, rest cut off as a
# scroll/expand cue" sizing the sentiment/news columns already use, just
# for prose height instead of a card count.
_ABOUT_COLLAPSED_HEIGHT = "320px"


def _about_collapse_fix_script() -> rx.Component:
    # A coin with a short description (e.g. Ondo's ~2 short paragraphs)
    # doesn't need the collapse/expand affordance at all — confirmed live
    # that always reserving _ABOUT_COLLAPSED_HEIGHT left a large, obviously
    # wasted empty gap below short text with an arrow that would only ever
    # "expand" onto more empty space. This measures the real rendered
    # content height once after mount (scrollHeight still reports the full
    # content even while clipped by overflow:hidden) and, if it already
    # fits within the collapsed height, switches to a natural max-content
    # height and hides the arrow entirely — left alone (still collapsed,
    # arrow visible) whenever the content genuinely overflows.
    return rx.script(
        "(function(){"
        "function check(){"
        "var inner=document.querySelector('.about-text-inner');"
        "var btn=document.querySelector('.about-expand-btn');"
        "if(!inner||!btn){return;}"
        "if(inner.scrollHeight<=inner.clientHeight+1){"
        "inner.style.height='max-content';"
        "btn.style.display='none';"
        "}"
        "}"
        "requestAnimationFrame(function(){requestAnimationFrame(check);});"
        "})();"
    )


def _about_section() -> rx.Component:
    # Real, free-text project description straight from CMC's /v2/info
    # payload (see app/services/market_data_service.py::_upsert_contracts —
    # same response website_url/whitepaper_url/etc. already come from, so
    # this is free: no new API call, just one more field persisted from a
    # response already fetched). Fixed collapsed height + a centered expand
    # arrow per explicit request (superseding this section's earlier
    # "always shown in full" design) — CoinState.about_expanded/
    # toggle_about_expanded drive it, and _about_collapse_fix_script above
    # removes the affordance entirely for short descriptions that never
    # actually overflow it.
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
                rx.box(
                    _highlighted_paragraph(coin["description_tokens"]),
                    height=rx.cond(CoinState.about_expanded, "auto", _ABOUT_COLLAPSED_HEIGHT),
                    overflow="hidden",
                    class_name="about-text-inner",
                ),
                # Centered expand/collapse arrow, half-overlapping the
                # clipped box's bottom edge — kept as a sibling of (not
                # inside) that overflow:hidden box so it's never itself
                # clipped away while collapsed.
                rx.box(
                    rx.cond(
                        CoinState.about_expanded,
                        rx.icon("chevron-up", size=16),
                        rx.icon("chevron-down", size=16),
                    ),
                    on_click=CoinState.toggle_about_expanded,
                    position="absolute",
                    bottom="-14px",
                    left="50%",
                    transform="translateX(-50%)",
                    width="28px",
                    height="28px",
                    border_radius="9999px",
                    background="var(--gray-5)",
                    display="flex",
                    align_items="center",
                    justify_content="center",
                    cursor="pointer",
                    class_name="about-expand-btn",
                ),
                _about_collapse_fix_script(),
                position="relative",
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


def _business_summary_section_block(section: dict) -> rx.Component:
    # A heading only shows when the model actually gave this paragraph one
    # (see CoinState._parse_business_summary_sections — older cached
    # summaries generated before the "TITLE:" prompt convention existed
    # fall back to a single untitled section).
    return rx.vstack(
        rx.cond(
            section["title"] != "",
            rx.text(section["title"], size="2", weight="bold"),
        ),
        _highlighted_paragraph(section["tokens"]),
        spacing="1",
        width="100%",
        align="start",
    )


def _business_summary_section() -> rx.Component:
    # Same styled text box as _about_section's inner container, but no
    # heading/icon row per explicit request — just the text container,
    # filled with an AI-generated (not CMC/CoinGecko-sourced) plain-language
    # explainer of what the coin does, its business model, and how it makes
    # money, aimed at someone new to crypto (see
    # app/services/business_summary_service.py). Each paragraph gets its own
    # short title above it (when the model provided one) since each covers a
    # distinct topic. A glowing outer shadow marks this card as worth
    # reading (explicit request), and the bottom credit row is
    # space-between: "Generated by AI" on the left, the actual model that
    # produced this text (brand logo + short name, e.g. "NVIDIA · Nemotron
    # 3 Ultra") on the right — CoinState._format_model_badge reads this
    # straight from the API response's own "model" field, not just whatever
    # settings.openrouter_model happens to be configured to right now, so
    # it stays accurate even after that default changes. Visually distinct
    # from _about_section's real CMC/CoinGecko-sourced text right above it.
    coin = CoinState.selected_coin
    badge = coin["business_summary_model_badge"].to(dict)
    return rx.cond(
        coin["has_business_summary"],
        rx.box(
            rx.vstack(
                rx.foreach(coin["business_summary_sections"].to(list[dict]), _business_summary_section_block),
                spacing="3",
                width="100%",
                align="start",
            ),
            rx.divider(margin_y="0.75em"),
            rx.hstack(
                rx.hstack(
                    rx.icon("sparkles", size=13, color="var(--gray-9)"),
                    rx.text("Generated by AI", size="1", color_scheme="gray", style={"font-style": "italic"}),
                    spacing="1",
                    align="center",
                ),
                rx.cond(
                    badge["model_display"] != "",
                    rx.badge(
                        _ai_provider_icon(badge["provider"], 12),
                        rx.text(badge["model_display"], size="1"),
                        color_scheme="gray",
                        variant="surface",
                        radius="full",
                    ),
                ),
                width="100%",
                justify="between",
                align="center",
                wrap="wrap",
            ),
            padding="1.25em",
            border_radius="10px",
            background="var(--gray-a2)",
            width="100%",
            # Reduced glow (was 0 0 24px 2px) + an explicit solid royalblue
            # border per explicit request — the border now does most of the
            # "this card is distinct" work, so the shadow only needs to be a
            # subtle accent rather than the primary cue.
            box_shadow="0 0 10px 1px var(--indigo-a4)",
            border="5px solid royalblue",
        ),
    )


def _market_pairs_filter_button(label: str, value: str) -> rx.Component:
    is_active = CoinState.market_pairs_filter == value
    return rx.box(
        rx.text(label, size="2", weight="medium"),
        on_click=CoinState.set_market_pairs_filter(value),
        padding="0.35em 1em",
        border_radius="8px",
        cursor="pointer",
        background=rx.cond(is_active, "var(--gray-a5)", "transparent"),
    )


def _market_pair_row(pair: dict, index: int) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(index + 1, size="2", color_scheme="gray")),
        rx.table.cell(
            rx.hstack(
                rx.cond(
                    pair["exchange_icon_url"] != "",
                    rx.image(src=pair["exchange_icon_url"], width="20px", height="20px", border_radius="4px"),
                    # CoinGecko's bulk exchange listing (see
                    # market_pairs_service.py's _get_exchange_logo_map) only
                    # covers centralized exchanges — a DEX (or any exchange
                    # it doesn't list) falls back to this rather than a
                    # broken image icon.
                    rx.box(
                        rx.icon("building-2", size=12),
                        width="20px",
                        height="20px",
                        border_radius="4px",
                        background="var(--gray-a4)",
                        display="flex",
                        align_items="center",
                        justify_content="center",
                        flex_shrink="0",
                    ),
                ),
                rx.text(pair["exchange_name"], size="2", weight="medium"),
                rx.badge(pair["market_type_label"], size="1", color_scheme=pair["market_type_color"], variant="surface"),
                spacing="2",
                align="center",
            ),
            vertical_align="middle",
        ),
        rx.table.cell(rx.text(pair["market_pair"], size="2"), vertical_align="middle"),
        rx.table.cell(rx.text(pair["price_display"], size="2"), vertical_align="middle"),
        rx.table.cell(rx.text(pair["volume_display"], size="2"), vertical_align="middle"),
        rx.table.cell(rx.text(pair["volume_pct_display"], size="2"), vertical_align="middle"),
        rx.table.cell(rx.text(pair["last_updated_display"], size="1", color_scheme="gray"), vertical_align="middle"),
        _hover={"background_color": "var(--gray-a3)"},
    )


def _market_pairs_section() -> rx.Component:
    # Real per-exchange price/volume from CoinGecko's free API (see
    # app/services/market_pairs_service.py's module docstring — CMC's own
    # equivalent endpoint 403s on this project's Basic/free CMC plan),
    # capped to the top 10 CEX + top 10 DEX by 24h volume per explicit
    # request. Open Interest/Funding Rate/Spread (derivatives-specific)
    # aren't shown — this data is spot-markets only on any free-tier
    # provider we use.
    coin = CoinState.selected_coin
    return rx.cond(
        coin["has_market_pairs"],
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.heading(coin["name"], " Markets", size="4"),
                    rx.text("Affiliate disclosures", size="1", color_scheme="gray"),
                    spacing="0",
                    align="start",
                ),
                rx.spacer(),
                rx.hstack(
                    _market_pairs_filter_button("All", "all"),
                    _market_pairs_filter_button("CEX", "cex"),
                    _market_pairs_filter_button("DEX", "dex"),
                    spacing="1",
                    background="var(--gray-a3)",
                    padding="0.25em",
                    border_radius="10px",
                ),
                width="100%",
                align="center",
                wrap="wrap",
            ),
            rx.box(
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("#"),
                            rx.table.column_header_cell("Exchange"),
                            rx.table.column_header_cell("Pair"),
                            rx.table.column_header_cell("Price"),
                            rx.table.column_header_cell("24h Volume"),
                            rx.table.column_header_cell("Volume %"),
                            rx.table.column_header_cell("Last Updated"),
                        ),
                    ),
                    rx.table.body(
                        rx.foreach(CoinState.filtered_market_pairs, _market_pair_row),
                    ),
                    variant="surface",
                    width="100%",
                ),
                overflow_x="auto",
                width="100%",
                class_name="visible-scrollbar",
            ),
            spacing="3",
            width="100%",
            align="start",
        ),
    )


def _chart_column() -> rx.Component:
    coin = CoinState.selected_coin
    return rx.vstack(
        rx.hstack(
            rx.heading(coin["name"], " Live Chart", size="4"),
            # AI-generated business-model classification (see
            # business_summary_service.py's CATEGORY: line) — more specific
            # than the broad CMC narrative tags shown elsewhere on this page
            # (e.g. "Real World Assets (RWA)" vs. this badge's "Tokenized
            # Public Funds / Treasuries"). Pulsing glow (see styles.css's
            # .category-badge-glow) marks it worth noticing; only renders
            # once the AI summary has actually generated one.
            rx.cond(
                coin["has_business_model_category"],
                rx.badge(
                    coin["business_model_category"],
                    color_scheme="indigo",
                    variant="surface",
                    radius="full",
                    size="2",
                    class_name="category-badge-glow",
                ),
            ),
            justify="between",
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
        _business_summary_section(),
        _market_pairs_section(),
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
