# Testing and documentation

## Verifying UI work
- Run browsers headless / in the background (Playwright MCP or the Claude-in-Chrome tools); never pop up visible windows for the user.
- Verify with real measurements (computed styles, bounding boxes, console messages), at 1440 / 834 / 375 px, in dark and light mode. Zero console errors is the bar (the dynamic-route 404 status is known).
- After a code change that Reflex compiles, restart per `process-management.md` and wait for HTTP 200.

## Documentation (single source of truth: `docs/`)
- Per-page state lives in `docs/<page>.md` (home, single-coin-page, news, narrative, chains, tools, watchlist, global-components), indexed by `docs/README.md`. Update the matching file in the same change when a page's behaviour changes. Shared UI (header, footer, profile menu, global search, floating widgets) goes in `docs/global-components.md`.
- Each page file lists Features and, per feature, how it works (use `<details><summary>` blocks).
- `docs/CHANGELOG.md` is the archived historical log (do not load it; do not add to it unless asked).
- Notion mirroring is OPTIONAL and only on request. If asked, the pages are children of "Crypto Intelligence Platform" and mirror `docs/`.
- Handoff: after significant work, add or refresh ONE line under "Current State" in CLAUDE.md (keep that section under ~20 lines) and any open item under "Open items".
