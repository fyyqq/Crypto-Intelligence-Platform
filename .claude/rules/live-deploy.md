# Live deployment (Contabo)

The live site is a **separate deployment** from local dev — a second clone of this
same repo running on its own server, with its own database. Pushing to GitHub
(Core rule 3) never reaches it by itself; deploying there is a distinct,
explicit step, done only when the user asks (see trigger phrases below).

## Where it lives

- **Site**: https://repace.fyqqflow.com — **Contabo** Cloud VPS 4, IP `207.180.233.86`.
- **SSH**: `ssh deploy@repace.fyqqflow.com` — key-based, already set up from this
  Mac, no password needed. `deploy` does **not** have passwordless `sudo`:
  any `sudo` step (service restarts, systemd units) must be run by the user in
  their own terminal (`ssh -t deploy@repace.fyqqflow.com 'sudo ...'`). Never
  ask for the sudo password in chat.
- **Code**: `/home/deploy/repace` on the server — a separate `git clone` of
  `fyyqq/Crypto-Intelligence-Platform`, not a shared filesystem with this Mac.
  Never edit files directly on the server; it only moves forward via
  `git pull`, and a hand-edit there just means the next pull conflicts with it
  or silently gets overwritten.
- **Database**: the server runs its **own** Postgres, entirely separate data
  from local dev (`docker-compose`'s `localhost:5432`). Local testing never
  touches live data and vice versa. A migration has to be run **on the
  server, against its own DB** — pulling new code there does not run it.
- **`.env` on the server** is its own file (gitignored, not pulled from
  GitHub) — copied there once via `scp`. A new required env var/API key
  needs manually adding to the server's `.env` too; `git pull` won't bring it.
- **Processes** (systemd, both `enable`d so they survive a reboot):
  `repace-reflex.service` (the Reflex app) and
  `repace-telegram-listener.service` (the listener). nginx + certbot already
  handle HTTPS in front of it — not something to touch for a routine deploy.

## Server maintenance already in place

- **Nightly restart**: `repace-nightly-restart.timer` (+ `.service`, in
  `/etc/systemd/system/`) restarts only `repace-reflex.service` daily at
  `02:00 UTC` (10:00 MYT; the server clock is Europe/Berlin, so the unit
  names UTC explicitly). It frees the RAM Reflex builds up from per-session
  state (~4.6 GB after 5 days). Check: `systemctl list-timers repace-nightly-restart.timer`.
- **Monitoring**: Netdata v2 on port 19999, firewalled; open it via
  `ssh -L 19999:localhost:19999 deploy@repace.fyqqflow.com` then
  `http://localhost:19999`. The agent was auto-claimed to Netdata
  Cloud at install (`agent-claimed: true` as of 2026-10-11); disconnecting it
  needs a `sudo` step the user runs themselves. Check with
  `curl -s localhost:19999/api/v1/info` on the server. Tutorial: `docs/netdata-monitoring.md`.

## Deploy sequence (only when explicitly asked)

```bash
ssh deploy@repace.fyqqflow.com "
  cd ~/repace && git pull &&
  source .venv/bin/activate &&
  pip install -r requirements.txt &&
  alembic upgrade head &&
  sudo systemctl restart repace-reflex.service
"
```
- The final `sudo` line needs the password, so either the user runs the whole
  block with `ssh -t`, or Claude runs everything up to it and hands the
  restart to the user.
- `pip install` only actually changes anything if `requirements.txt` changed —
  harmless (fast no-op) to run every time regardless.
- `alembic upgrade head` is a no-op if there's no new migration — same,
  harmless to always run.
- Only restart `repace-telegram-listener.service` too if Telegram-pipeline
  code changed (`app/services/telegram_pipeline.py`, `telegram_listener.py`,
  `telegram_classifier.py`, `telegram_media_cleanup.py`) — restarting it
  needlessly is a minor one-time reconnect, not harmful, but unnecessary.
- If a new `Coin` model column was added, the server also needs its own
  `cd frontend && reflex db migrate` (the separate Reflex SQLite mirror —
  see `reflex-frontend.md`'s "both migrations" rule), same as locally.

## Verify after deploying — against the live URL, not localhost

```bash
curl -s -o /dev/null -w "%{http_code}\n" -m 15 https://repace.fyqqflow.com/
ssh deploy@repace.fyqqflow.com "systemctl is-active repace-reflex.service repace-telegram-listener.service"
```
Wait for a real `200` and both `active`, the same "verify, don't assume"
standard `testing-and-docs.md` already sets for local restarts.

## When to actually deploy

Only on an explicit request — phrases like "update the live site/server",
"deploy this", "push the new changes live", "update live". A plain "commit
and push" (Core rule 3) means GitHub only; don't deploy to Contabo unless
asked, even right after pushing. Local commits can pile up across several
sessions before a deploy is requested — that's expected, not a problem to fix.
