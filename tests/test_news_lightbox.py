"""The news reader photo viewer (assets/news_lightbox.js): static checks that it is wired to the reader."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_reader_photos_are_marked_and_the_script_is_loaded_on_the_reader_page():
    detail = (ROOT / "frontend" / "frontend" / "components" / "news_detail.py").read_text()
    assert detail.count("news-photo") == 2  # the media grid photo and the single hero image; related-news thumbnails and videos are not marked
    page = (ROOT / "frontend" / "frontend" / "frontend.py").read_text()
    reader = page[page.index("def news_detail_page"):page.index("def narrative_page")]
    assert '"/news_lightbox.js"' in reader


def test_the_viewer_has_arrows_keys_swipe_and_skips_fallback_images():
    js = (ROOT / "frontend" / "assets" / "news_lightbox.js").read_text()
    for needle in ('data-nlb="prev"', 'data-nlb="next"', '"ArrowRight"', '"ArrowLeft"', '"Escape"', "touchend", "fallback-image|_avatar_"):
        assert needle in js
    css = (ROOT / "frontend" / "assets" / "styles.css").read_text()
    assert ".news-lightbox.nlb-open" in css and ".nlb-prev" in css and ".nlb-next" in css
