"""One-time download of the local Malay translation model (NLLB-200 distilled 600M, CTranslate2 int8) into models/ (git-ignored).

    python -m scripts.download_translation_model

About 630 MB. The weights are Meta's NLLB-200 (licence CC-BY-NC-4.0: non-commercial) converted for CTranslate2 by a third party on
Hugging Face; the files are plain binary + text (no pickled code). Files that are already complete are skipped, so re-running is safe.
app/services/local_translate_service.py uses the folder; nothing else needs the network afterwards."""

import sys
from pathlib import Path

import requests

REPO = "JustFrederik/nllb-200-distilled-600M-ct2-int8"
FILES = ["config.json", "model.bin", "sentencepiece.bpe.model", "shared_vocabulary.txt", "special_tokens_map.json", "tokenizer_config.json"]
TARGET = Path(__file__).resolve().parent.parent / "models" / "nllb-600m-ct2-int8"


def main() -> int:
    TARGET.mkdir(parents=True, exist_ok=True)
    sizes = {s["rfilename"]: s.get("size") for s in requests.get(f"https://huggingface.co/api/models/{REPO}?blobs=true", timeout=30).json()["siblings"]}
    for name in FILES:
        dest = TARGET / name
        want = sizes.get(name)
        if dest.exists() and want and dest.stat().st_size == want:
            print(f"ok      {name} (already here)")
            continue
        print(f"get     {name} ...", flush=True)
        part = dest.with_suffix(dest.suffix + ".part")
        with requests.get(f"https://huggingface.co/{REPO}/resolve/main/{name}", stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(part, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        if want and part.stat().st_size != want:
            part.unlink()
            print(f"FAILED  {name}: size {want} expected", file=sys.stderr)
            return 1
        part.rename(dest)
    print("done:", TARGET)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
