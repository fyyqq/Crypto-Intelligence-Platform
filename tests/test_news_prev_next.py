"""News reader: previous / next article in the same category at the top of the article and of "Other News Related"."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "frontend"))


def _row(i, news_type="Cryptocurrency", title=None):
    return {"id": i, "news_type": news_type, "title": title if title is not None else f"Story {i}", "detail_url": f"/news/x/story-{i}"}


def test_neighbours_are_the_next_newer_and_next_older_story_of_the_same_category():
    from frontend.state.news_state import _neighbors

    newest_first = [_row(5), _row(4, "AI"), _row(3), _row(2, "AI"), _row(1)]
    got = _neighbors(newest_first, newest_first[2])  # id 3: the crypto stories are 5, 3, 1
    assert got["prev"]["detail_url"] == "/news/x/story-5" and got["next"]["detail_url"] == "/news/x/story-1"  # the AI ones are skipped
    assert _neighbors(newest_first, newest_first[0])["prev"] is None  # the newest has no Previous
    assert _neighbors(newest_first, newest_first[4])["next"] is None  # the oldest has no Next
    assert _neighbors([_row(9, title="")], _row(9))["prev"] is None
    only = _neighbors([_row(1), _row(2, title="")], _row(1))
    assert only["next"]["title"] == "Untitled"  # a story without a title still gets a link


def test_neighbours_carry_a_picture_and_an_excerpt_for_the_hover_popup():
    from frontend.state.news_state import _build_article_detail, _neighbor_fields, _neighbors

    rows = [
        {**_row(2), "image_url": "/img/2.webp", "fallback_image_url": "/fb/2.webp", "snippet": "Second story excerpt.", "has_snippet": True},
        {**_row(1), "image_url": "/img/1.webp", "fallback_image_url": "/fb/1.webp", "snippet": "hidden", "has_snippet": False},
    ]
    got = _neighbors(rows, rows[0])
    assert got["prev"] is None and got["next"]["image_url"] == "/img/1.webp" and got["next"]["snippet"] == ""  # no excerpt when the story has none
    back = _neighbors(rows, rows[1])
    assert back["prev"]["snippet"] == "Second story excerpt." and back["prev"]["fallback_image_url"] == "/fb/2.webp"
    fields = _neighbor_fields("prev", back["prev"])
    assert fields["has_prev"] and fields["prev_image"] == "/img/2.webp" and fields["prev_snippet"] == "Second story excerpt."
    none = _neighbor_fields("next", None)  # the newest story: no Previous, so nothing at all for it
    assert none["has_next"] is False and none["next_url"] == "" and none["next_title"] == "" and none["next_image"] == ""
    assert _build_article_detail(None, [], {}) == {}


def test_the_neighbours_are_one_full_width_row_above_the_article_and_the_sidebar():
    src = (ROOT / "frontend" / "frontend" / "components" / "news_detail.py").read_text()
    assert src.count('_prev_next(article, "top"),') == 1 and src.count('_prev_next(article, "after-source"),') == 1 and "in_sidebar" not in src
    reader = src[src.index("def _reader"):src.index("def _not_found")]
    assert reader.index('_prev_next(article, "top"),') < reader.index("rx.grid(") < reader.index("_article_metadata(article)") < reader.index("_article_sidebar(article)")  # above both columns on desktop
    side = src[src.index("def _article_sidebar"):src.index("def _body_segment")]
    assert side.index("_source_link(article),") < side.index('_prev_next(article, "after-source"),') < side.index('rx.heading("Other News Related"')  # tablet / phone: under the article source
    assert "@media (min-width: 1024px) { .news-nav-after-source { display: none; } }" in (ROOT / "frontend" / "assets" / "styles.css").read_text()
    assert "@media (max-width: 1023px) { .news-nav-top { display: none; } }" in (ROOT / "frontend" / "assets" / "styles.css").read_text()
    card = src[src.index("def _nav_card"):src.index("def _prev_next")]
    assert "news-nav-img" in card and "_title" in card and "_snippet" in card  # picture left, title + excerpt right
    assert "_hover" not in card and "popup" not in card.lower()  # no hover effect: the card is just there
    assert "def _nav_popup" not in src and "news-nav-pop" not in src
    css = (ROOT / "frontend" / "assets" / "styles.css").read_text()
    assert ".news-nav-card-next { grid-template-columns: 120px minmax(0, 1fr) auto; }" in css and ".news-nav-card-prev { grid-template-columns: auto 120px minmax(0, 1fr); }" in css
    assert ".news-nav-main .news-nav-next { grid-column: 2; }" in css
    assert "news-nav-side" not in css and "news-nav-side" not in src  # the sidebar variant is gone
    assert ".news-nav-arrow { flex: none; color: var(--gray-12);" in css and "scaleX(-1)" in css  # theme colour, flipped on Previous
    assert "_double_chevron()" in card and "[arrow, image, text] if prefix == \"prev\" else [image, text, arrow]" in card  # left of Previous, right of Next
    state = (ROOT / "frontend" / "frontend" / "state" / "news_state.py").read_text()
    assert 'f"has_{prefix}": bool(item)' in state
    # a side with no neighbour is not rendered at all (no empty disabled card)
    assert src.count('rx.cond(article["has_prev"], _nav_card(') == 1 and src.count('rx.cond(article["has_next"], _nav_card(') == 1


def test_the_reader_no_longer_has_the_all_news_back_link():
    src = (ROOT / "frontend" / "frontend" / "components" / "news_detail.py").read_text()
    assert "All news" not in src
