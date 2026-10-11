# Netdata: Live Server Monitoring (Tutorial)

Netdata shows the **live Contabo server** (`repace.fyqqflow.com`, IP `207.180.233.86`) in real time: RAM, CPU, disk, network, and per-process usage. It runs on the server, not on your Mac, so it shows the live site's numbers, not your local dev machine.

It is **private**: port 19999 is blocked from the internet, so the dashboard is only reachable through an SSH tunnel from your computer. No public URL exists on purpose.

## How to open it

1. **Open a terminal** on your Mac (Terminal app or the VS Code terminal).
2. **Start the tunnel** by running:
   ```bash
   ssh -L 19999:localhost:19999 deploy@repace.fyqqflow.com
   ```
   It logs you into the server. Leave this window open: the tunnel only works while it is open.
3. **Open your browser** and go to: **http://localhost:19999** (note: 19999, five digits).
4. The dashboard loads. Use it while the terminal window stays open.
5. **When finished**, type `exit` in the terminal (or press Ctrl+D) to close the tunnel. The dashboard stops loading, which is expected.

## What to look at

| Where in Netdata | What it tells you |
|---|---|
| **System Overview → RAM** | Used vs. free memory. The Reflex app is the big user (several GB after days of uptime). |
| **Applications → Memory** | Which process is using the RAM (`python3` = Reflex, `python -m app.services.telegram_listener` = Telegram listener, `postgres`). |
| **Disks** | Disk space used (96 GB disk). Watch `telegram_media` and `.web` growth. |
| **CPU** | Spikes during syncs and news catch-up are normal. |
| **Alerts** (bell icon) | Netdata warns when RAM or disk gets high. |

## Common problems

- **"Address already in use" on step 2**: an old tunnel is still open. Close the other terminal, or use a different local port: `ssh -L 19998:localhost:19999 deploy@repace.fyqqflow.com` then open `http://localhost:19998`.
- **Page does not load**: the SSH window was closed, or you typed the wrong port (it is `19999`, not `9999`).
- **From your phone**: not possible while the Mac is off or asleep, since the tunnel runs from the Mac. Contabo's own dashboard (my.contabo.com) shows basic CPU/network graphs from anywhere.
- **"Free trial" or Netdata Cloud messages**: the local dashboard on the server is free permanently. The trial messaging is for the optional Netdata Cloud connection; the agent was auto-claimed to it during install and can be disconnected to stay local-only.

## Nightly restart (RAM cleanup)

The Reflex app grows in memory over days (per-visitor server state). A systemd timer `repace-nightly-restart.timer` restarts only `repace-reflex.service` daily at **02:00 UTC = 10:00 Malaysia time**, which returns it to its fresh-start memory level. Postgres, the Telegram listener, and all data are untouched. Visitors connected at that moment see a 10-20 second reconnect.

- Check the schedule: `ssh deploy@repace.fyqqflow.com "systemctl list-timers repace-nightly-restart.timer"`
- Turn it off: `sudo systemctl disable --now repace-nightly-restart.timer` (run on the server, needs the sudo password)
