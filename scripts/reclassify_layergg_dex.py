"""One-off: moves the already stored @layergg posts whose headline contains the word DEX ("What happened in DEX in
the last ~24h") from the Crypto to the Memecoins news section (new posts are routed by telegram_pipeline.store_message).
Safe to run again. Usage: python -m scripts.reclassify_layergg_dex"""
from sqlalchemy import text

from app.core.database import SessionLocal
from app.services.telegram_pipeline import DEX_POST_GROUP, is_dex_post


def main() -> int:
    db = SessionLocal()
    try:
        rows = db.execute(
            text("SELECT id, title FROM news_articles WHERE url LIKE :u AND category_or_query = 'Telegram Crypto'"),
            {"u": f"https://t.me/{DEX_POST_GROUP}/%"},
        ).all()
        ids = [r[0] for r in rows if is_dex_post(DEX_POST_GROUP, r[1] or "")]
        if ids:
            db.execute(text("UPDATE news_articles SET category_or_query = 'Telegram Memecoin' WHERE id = ANY(:ids)"), {"ids": ids})
            db.commit()
        print(f"moved {len(ids)} layergg DEX posts to Memecoins")
        return len(ids)
    finally:
        db.close()


if __name__ == "__main__":
    main()
