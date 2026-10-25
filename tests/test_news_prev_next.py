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


def test_the_article_detail_carries_the_links_and_both_places_use_them():
    from frontend.state.news_state import _build_article_detail

    assert _build_article_detail(None, [], {}) == {}
    src = (ROOT / "frontend" / "frontend" / "components" / "news_detail.py").read_text()
    assert src.count("_prev_next(article,") == 2  # top of the article column and top of "Other News Related"
    assert src.index('_prev_next(article, "1")') < src.index('rx.heading("Other News Related"')
    state = (ROOT / "frontend" / "frontend" / "state" / "news_state.py").read_text()
    assert '"has_prev": bool(prev_item)' in state and '"next_url"' in state
