---
paths:
  - "frontend/**"
---

# Reflex frontend rules

- **Never reassign `CoinState.all_coins`** after the first load (it serializes to ~32 MB over the websocket). Background refreshers merge patches into `coin_overrides` (keyed by `cmc_id`); read through `_row_with_overrides` / `_merged_row`.
- **`sys.path`**: any frontend function that does `from app...` must first insert the repo root (Reflex only has `frontend/` on the path), as the other handlers in `coin_state.py` do.
- **New `Coin` columns need both models and both migrations**: Postgres (`app/models/coin.py`, root `alembic`) and the Reflex SQLite mirror (`frontend/frontend/models/coin.py`, `reflex db makemigrations` + `reflex db migrate`); also mirror in `reflex_cache_service`.
- **Radix breakpoints** (pixel values): xs 520, sm 768, md 1024, lg 1280, xl 1640. `md` is NOT tablet.
- **Styling**: Radix rules sit in a CSS `@layer` and outrank plain class rules. Use inline style, `!important`, or a raw `rx.el.*` element when a class loses. `rx.grid` ignores `gap`; use `spacing`.
- `assets/styles.css` and `assets/*.js` are build-time copies: restart Reflex after editing.
- **Links**: anything that moves to another page is an `rx.link(href=...)` (real `<a>`), not an `on_click` handler. Use `.row-link` / `.row-interactive` for stretched row links. `chain_pills.js` turns plain same-origin anchor clicks into full page loads.
- Never use `rx.html` for iframes (re-renders reset the widget). Use `rx.el.iframe` with a real `src` prop.
- Inside `rx.foreach` an untyped dict value needs `.to(str)` before string methods; `_news_card(..., compact=)` is keyword-only because foreach passes an index.
- Verify icon fill with `getComputedStyle`, not the SVG attribute. Dynamic routes (`/coin/[symbol]`, `/news/<cat>/<slug>`) return an HTTP 404 status on a hard load under `--single-port` but render; this is a known hosting quirk.
- **Theme**: never hardcode white/black or fixed hex for text on themed surfaces; use `var(--gray-12)` / `var(--gray-11)` or `rx.color_mode_cond`. Cards use `var(--gray-a2)` / `var(--gray-2)`. Fixed white is allowed only on royalblue/accent badges, dark image overlays, toasts, and `/login` + `/signup`. After UI changes, check light mode (`localStorage.theme = "light"`) and contrast (>= 3:1).
- **Header budget at 375px is tight** (70px search, logo text hidden < 480px). Re-measure with `getBoundingClientRect` before adding a header element.
