"""Runs one news-pipeline catch-up (app.scheduler.jobs.run_news_pipeline_sync)
as its own process: `python -m app.scheduler.news_job`.

The pipeline takes ~25 minutes of CPU-heavy parsing per run and is due every
NEWS_PIPELINE_SYNC_INTERVAL_HOURS (0.5), so run as a thread inside the web
server it kept the server's global interpreter lock busy most of the time and
every page load queued behind it (5-40s waits on the live site, measured
2026-10-13). frontend/news_catchup.py starts this at low priority instead.
"""

from app.scheduler.jobs import run_news_pipeline_sync

if __name__ == "__main__":
    run_news_pipeline_sync()
