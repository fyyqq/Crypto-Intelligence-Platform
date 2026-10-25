"""Local offline Malay translation (app/services/local_translate_service.py): sentence splitting, the small glossary, the no-model case,
and (only when the model has been downloaded) a real translation."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services import local_translate_service as svc  # noqa: E402


def test_texts_are_split_into_sentences_and_long_ones_are_cut():
    assert svc.split_sentences("One thing. Another thing! A third? Yes.") == ["One thing.", "Another thing!", "A third?", "Yes."]
    assert svc.split_sentences("Rate: 22% on gains. Current deadline: January 2027.") == ["Rate: 22% on gains.", "Current deadline: January 2027."]
    assert svc.split_sentences("   ") == [] and svc.split_sentences("") == []
    long = ", ".join(["a clause of several words"] * 40) + "."
    parts = svc.split_sentences(long)
    assert len(parts) > 1 and all(len(p) <= 401 for p in parts) and " ".join(parts).replace("  ", " ") == long


def test_the_glossary_fixes_the_known_crypto_mistakes():
    pre = svc._apply(svc._PRE_EDITS_MS, "liquidity safeguards for won-denominated stablecoins")
    assert pre == "liquidity safeguards for stablecoins denominated in the South Korean won currency"  # "won" is not "kemenangan" (victory)
    post = lambda text: svc._apply(svc._POST_EDITS_MS, text)  # noqa: E731
    assert post("memperluaskan tokenizasi kepada aset") == "memperluaskan tokenisasi kepada aset"
    assert post("teknologi buku besar terbahagi") == "teknologi lejar teragih"
    assert post("cukai crypto 22%") == "cukai kripto 22%"
    assert post("perdagangan cryptocurrency") == "perdagangan mata wang kripto"
    assert post("lihat Crypto.com dan JUST IN: berita") == "lihat Crypto.com dan TERKINI: berita"  # a name like Crypto.com is left alone


def test_without_the_model_folder_translating_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(svc.settings, "translation_model_dir", str(tmp_path / "missing"))
    assert svc.is_available() is False
    assert svc.translate_texts(["Hello"], "ms") is None
    monkeypatch.setattr(svc.settings, "translation_model_dir", str(tmp_path))
    assert svc.translate_texts(["Hello"], "fr") is None  # only the offered languages


@pytest.mark.skipif(not svc.is_available(), reason="the translation model is not downloaded (python -m scripts.download_translation_model)")
def test_a_real_translation_keeps_numbers_and_names_and_one_result_per_text():
    out = svc.translate_texts(["The token price rose 35% in 24 hours.", "", "Kyrgyzstan has shut down USDKG."], "ms")
    assert len(out) == 3 and out[1] == ""
    assert "35%" in out[0] and out[0] != "The token price rose 35% in 24 hours."
    assert "Kyrgyzstan" in out[2] and "USDKG" in out[2]
