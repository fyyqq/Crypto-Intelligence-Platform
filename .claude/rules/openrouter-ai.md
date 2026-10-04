---
paths:
  - "app/services/*summary*"
  - "app/services/*ai*"
  - "app/services/news_targeting_service.py"
  - "app/services/news_category.py"
  - "app/services/coin_category_service.py"
  - "app/services/telegram_classifier.py"
---

# OpenRouter / AI rules

- The account is free-tier: only `:free` models, ~50 requests/day TOTAL (shared by every feature). Paid models 402.
- Every call goes through `app/services/ai_budget.py` (hourly cap `openrouter_max_calls_per_hour`, per-item failure cooldown). Upstream 503 can arrive as HTTP 200 with an error body; services retry, then fall back through the alternate free models.
- Calls are normally triggered by a viewer opening a page and cached (news summary, coin business summary, coin description). Agreed exceptions that run outside a page visit: Telegram post classification (at arrival), news targeting/categorization (`news_catchup.py` worker), weekly coin-category re-check, daily "What happened today" (first click of the day).
- Prompts must forbid inventing facts beyond the provided text.
- Existing labels written by Claude Code (`target_model='claude-code'`, `category_source='claude-code'`, summary model `claude-code`) are judgments, not facts; clear the row's timestamp to let the AI redo it.
- AI-generated text must be theme-aware (`var(--gray-12)`), never hardcoded white.
