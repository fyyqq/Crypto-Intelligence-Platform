from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routers import categories, coins, health
from app.scheduler.jobs import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(title="Crypto Intelligence Platform", lifespan=lifespan)

    app.include_router(health.router)
    app.include_router(coins.router)
    app.include_router(categories.router)

    return app


app = create_app()
