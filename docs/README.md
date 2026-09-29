# Crypto Intelligence Platform — Page & Component Reference

Local, git-tracked mirror of this project's Notion documentation — one file per actual site page/component, named the same as its Notion counterpart. Exists so a fresh session (Claude Code or GitHub Copilot) can read "what does this page actually do, and how" straight from the repo, without needing Notion access at all.

Each file: a status line (route, live vs. placeholder, source files), then a **Features** list — every distinct piece of functionality that page/component has, and *how it works* (real implementation detail, not just a feature name).

This folder, the matching [Notion pages](https://app.notion.com/p/3e1143f80527802d85a2e6c9801a150b), and `CLAUDE.md`'s own `### Feature 1`/`### Feature 2`/`### 🌐 Global Components` summary sections are all expected to describe the same current state. See `CLAUDE.md`'s **Documentation Sync Rule** — any change that updates a Notion page here also updates the matching file below, in the same pass, not eventually.

## Pages

| Page | Route | Status |
|---|---|---|
| [Home](./home.md) | `/` | Live |
| [Single Coin Page](./single-coin-page.md) | `/coin/[symbol]` | Live |
| [News](./news.md) | `/news` | Live |
| [Narrative](./narrative.md) | `/narrative` | Placeholder |
| [Chains](./chains.md) | `/chains` | Placeholder |
| [Tools](./tools.md) | `/tools` | Placeholder |
| [Watchlist](./watchlist.md) | `/watchlist` | Live |

## Shared

| Component | Renders on |
|---|---|
| [Global Components](./global-components.md) | Every page above — header/navbar, footer, floating logo, profile menu, global search |
