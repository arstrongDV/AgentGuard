import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, demo, events, llm, mcp, prometheus
from app.config import Settings, settings as default_settings
from app.services import Services

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or default_settings

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        services = Services(settings)
        app.state.services = services
        stop = asyncio.Event()
        tasks = [asyncio.create_task(services.load_models()), asyncio.create_task(services.poll_feed(stop))]
        if settings.watch_policy:
            tasks.append(asyncio.create_task(services.watch(stop)))
            tasks.append(asyncio.create_task(services.reconcile(stop)))
        try:
            yield
        finally:
            stop.set()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await services.aclose()

    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-agentguard-decision", "x-agentguard-trace-id", "x-agentguard-risk"],
    )

    @app.get("/")
    def read_root():
        return {"message": f"{settings.app_name} is running"}

    app.include_router(admin.router)
    app.include_router(prometheus.router)
    app.include_router(demo.router)
    app.include_router(events.router)
    app.include_router(llm.router)
    app.include_router(mcp.router)
    return app


app = create_app()
