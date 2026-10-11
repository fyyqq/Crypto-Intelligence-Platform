# GitHub Copilot Project Execution Rules

You are continuing work started in Claude Code on the Repace crypto platform (Reflex frontend in `frontend/`, FastAPI + Postgres in `app/`). Match its architecture, naming, comment density and active task. The repo's own docs are the source of truth, not your memory.

## Read first (before writing or changing code)

1. `CLAUDE.md` in the project root: **Core rules**, **Current State** (latest work) and **Open items** (known gaps).
2. The `.claude/rules/*.md` files that match what you are editing. Copilot does not load them automatically, so open them yourself:
   - `reflex-frontend.md`: any file in `frontend/` (never reassign `CoinState.all_coins`, Radix breakpoints, links, theme)
   - `process-management.md`: starting, stopping or restarting anything
   - `telegram-news.md`: Telegram, news, `news_state.py`
   - `coin-page-tradingview.md`: coin page, prices, chart
   - `openrouter-ai.md`, `auth-sessions.md`: AI features, login
   - `live-deploy.md`: anything about the live site
   - `testing-and-docs.md`: how to verify and document
3. `docs/README.md`, then the matching `docs/<page>.md` for the page you are changing.

## Hard rules

- **Prices**: format every USD price through `coin_state._fmt_usd`. Never a fixed-decimal f-string.
- **Theme**: use `var(--gray-12)` / `var(--gray-11)` / `var(--gray-a2)`. Never hardcode white or black on themed surfaces. Check light and dark mode.
- **Git**: `git diff` first, then `git add <specific files>`. Never `git add -A`. Uncommitted edits you did not make may be another session's work, so leave them alone. Push to `origin main` (the owner GitHub account is `fyyqq`).
- **Processes**: exactly one Reflex process pair (ports 3000/3001) and one Telegram listener. Stop old PIDs first, never chain kill and restart, and wait for a real HTTP 200 after a restart.
- **Live site** (https://repace.fyqqflow.com, Contabo): deploy only when the user explicitly asks. Pushing to GitHub does not deploy. It has its own code clone and database. The domain now sits behind Cloudflare, so SSH must use the IP (`deploy@207.180.233.86`). `deploy` has no passwordless sudo: the user runs any `sudo` step themselves, and you never ask for the password.
- Do not read `docs/CHANGELOG.md` (archived, large).

## Verification

You cannot use Claude's browser tools (Playwright MCP, Claude-in-Chrome) or the Notion tools. Do not claim a UI change is verified. Say what you changed and give the user the manual check: URL, viewport widths (1440 / 834 / 375), dark and light mode, and the browser console must show no errors.

## When you finish

- Update the matching `docs/<page>.md` in the same change.
- Add or refresh one line under **Current State** in `CLAUDE.md` (keep that section under ~20 lines) and any open item under **Open items**.
- Ask the user whether to commit and push, then do it with specific files only.
