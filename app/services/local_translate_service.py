"""Local, offline English -> Malay translation (no API, no key, no daily limit): Meta's NLLB-200 distilled 600M model run with
CTranslate2 (int8, CPU). Used by the news reader's EN | MY tabs (news_summary_service); usable by any other page that needs a Malay
(or other NLLB language) text: `translate_texts(["Hello"], "ms")`.

* The model lives in models/nllb-600m-ct2-int8 (git-ignored, ~630 MB, fetched once by `python -m scripts.download_translation_model`).
  It is loaded the first time it is needed and kept (about 1 GB of RAM); with no model folder every call just returns None.
* Licence: NLLB-200 is CC-BY-NC-4.0 (non-commercial).
* NLLB translates best one sentence at a time, so each text is split into sentences, the sentences of ALL the texts of a call go
  through the model as one batch, and the pieces are joined back per text. Translations are serialized (one at a time) and the
  model uses `translation_threads` CPU threads (default 2 of the server's 4) so the website keeps its share of the CPU.
"""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

# NLLB's own language codes for the languages we offer.
LANGS = {"ms": "zsm_Latn", "en": "eng_Latn"}
SOURCE = "eng_Latn"

_lock = threading.Lock()
_loaded: dict = {}


def model_dir() -> Path:
    path = Path(settings.translation_model_dir)
    return path if path.is_absolute() else Path(__file__).resolve().parent.parent.parent / path


def is_available() -> bool:
    """True when the model files are on disk and the runtime packages are installed."""
    folder = model_dir()
    if not ((folder / "model.bin").is_file() and (folder / "sentencepiece.bpe.model").is_file()):
        return False
    try:
        import ctranslate2  # noqa: F401
        import sentencepiece  # noqa: F401
    except ImportError:
        return False
    return True


def _model():
    """The loaded (translator, tokenizer), loading them on first use. Call with _lock held."""
    if not _loaded:
        import ctranslate2
        import sentencepiece

        folder = model_dir()
        tokenizer = sentencepiece.SentencePieceProcessor()
        tokenizer.load(str(folder / "sentencepiece.bpe.model"))
        translator = ctranslate2.Translator(
            str(folder), device="cpu", compute_type="int8", intra_threads=max(1, int(settings.translation_threads)), inter_threads=1
        )
        _loaded.update(translator=translator, tokenizer=tokenizer)
        logger.info("Local translation model loaded from %s", folder)
    return _loaded["translator"], _loaded["tokenizer"]


# Small fixes around the model for crypto news, Malay only. Source side: wording the model mistranslates (the Korean "won" currency came
# out as "kemenangan" = victory). Target side: spelling / term fixes, applied to the model's output.
_PRE_EDITS_MS = [
    (re.compile(r"\b[Ww]on-denominated (\w+)"), r"\1 denominated in the South Korean won currency"),
]
_POST_EDITS_MS = [
    (re.compile(r"\b([Tt])okeniz?asi\b"), r"\1okenisasi"),
    (re.compile(r"\b[Bb]uku besar terbahagi\b"), "lejar teragih"),
    (re.compile(r"\b[Cc]ryptocurrenc(?:y|ies)\b"), "mata wang kripto"),
    (re.compile(r"\b[Cc]rypto\b(?!\.|currenc)"), "kripto"),
    (re.compile(r"\bJUST IN:"), "TERKINI:"),
]


def _apply(edits, text: str) -> str:
    for pattern, replacement in edits:
        text = pattern.sub(replacement, text)
    return text


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[\"'“‘(\[]?[A-Z0-9])")


def split_sentences(text: str) -> list[str]:
    """One text as sentences (NLLB's sweet spot); a very long sentence is cut at a comma or space so it stays well under the model's limit."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    out: list[str] = []
    for sentence in _SENTENCE_END.split(text):
        sentence = sentence.strip()
        while len(sentence) > 400:
            cut = max(sentence.rfind(", ", 0, 400), sentence.rfind(" ", 0, 400))
            cut = cut if cut > 100 else 400
            out.append(sentence[:cut + 1].strip())
            sentence = sentence[cut + 1:].strip()
        if sentence:
            out.append(sentence)
    return out


def translate_texts(texts: list[str], target: str = "ms") -> list[str] | None:
    """Translates each English text to `target` ("ms" = Malay); the result has one string per input (an empty input stays empty).
    None when the model is not installed or translating failed (the caller falls back to something else). Blocking: call it from a thread."""
    code = LANGS.get(target)
    if code is None or not is_available():
        return None
    pre = _PRE_EDITS_MS if target == "ms" else []
    pieces = [split_sentences(_apply(pre, t)) for t in texts]
    flat = [s for group in pieces for s in group]
    if not flat:
        return [""] * len(texts)
    try:
        with _lock:
            translator, tokenizer = _model()
            sources = [[SOURCE, *tokenizer.encode(s, out_type=str), "</s>"] for s in flat]
            results = translator.translate_batch(
                sources,
                target_prefix=[[code]] * len(sources),
                beam_size=max(1, int(settings.translation_beam_size)),
                no_repeat_ngram_size=3,
                repetition_penalty=1.1,
                max_decoding_length=256,
                max_batch_size=8,
            )
        post = _POST_EDITS_MS if target == "ms" else []
        done = []
        for result in results:
            tokens = result.hypotheses[0]
            if tokens and tokens[0] == code:
                tokens = tokens[1:]
            done.append(_apply(post, tokenizer.decode(tokens).strip()))
    except Exception:  # noqa: BLE001 - a model / memory problem must never break the page
        logger.exception("Local translation failed")
        return None
    out, i = [], 0
    for group in pieces:
        out.append(" ".join(done[i:i + len(group)]).strip())
        i += len(group)
    return out
