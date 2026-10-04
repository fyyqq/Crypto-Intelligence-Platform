# Process management

- Run the app as `reflex run --env prod --single-port` (port 3000; 3001 is the backend). Exactly ONE process pair.
- **Restart**: stop the old PIDs one at a time (`for p in $(lsof -ti :3000 :3001); do kill -INT $p; done`), confirm both ports are clear, then start with a single `run_in_background` call. No extra `&` / `nohup` (it double-launches).
- Never chain kill + restart in one command. Wait for an actual HTTP 200 on `/`, not a "ready" log line.
- A `Prerender: Request failed for /: ... timeout` build error is transient; retry.
- **Telegram listener** (`python -m app.services.telegram_listener > telegram_listener.log 2>&1`): exactly ONE process (SQLite session, two = `database is locked`). Find it with `ps aux | grep -i telegram_listener` (macOS shows `Python`, capital P); kill every match and confirm none remain before starting. Don't run `telegram_pipeline.py` one-shot or the Sarjana backfill while it runs (stop, run, restart). `frontend/news_catchup.py` also starts it when `/news` loads.
- If `database is locked` recurs with one listener, move `telegram_session.session` out of `~/Documents` (iCloud File Provider) and update `SESSION_PATH` in `telegram_pipeline.py` and `scripts/telegram_login.py`.
- Never hold an open DB transaction while code runs `ALTER TABLE` / `ADD COLUMN`; check `information_schema` first and use a 3s lock timeout.
