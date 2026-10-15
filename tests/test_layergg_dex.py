"""@layergg posts about DEX go to the Memecoins section (headline contains the word DEX)."""

import pytest

pytest.importorskip("telethon")
from app.services.telegram_pipeline import is_dex_post  # noqa: E402


def test_only_layergg_posts_with_the_word_dex_in_the_headline():
    assert is_dex_post("layergg", "🆘 What happened in DEX in the last ~24h🆘\n\nlots of text")
    assert is_dex_post("layergg", "What happened in Dex in the last ~72h") and is_dex_post("layergg", "Top dexs today") and is_dex_post("layergg", "New DEXes")
    assert not is_dex_post("layergg", "Circle Arc is coming\n\nan indexed DEX launches")  # DEX only in the body
    assert not is_dex_post("layergg", "Why indexed funds win") and not is_dex_post("layergg", "Dexter returns")  # not the word
    assert not is_dex_post("WatcherGuru", "What happened in DEX in the last ~24h") and not is_dex_post("layergg", "")
