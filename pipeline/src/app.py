#!/usr/bin/python3

import os
import uvicorn
from fastapi import FastAPI

from plombery._version import __version__
from plombery.websocket import asgi
from plombery.api.middlewares import SPAStaticFiles, setup_cors
from plombery.api.authentication import build_auth_router
from plombery.api.routers import pipelines, runs, tokens

from src import seek_spider_pipeline  # noqa: F401
from src.api.jobs import router as jobs_router

API_PREFIX = "/api"


def create_app():
    app = FastAPI(title="Plombery", version=__version__, redirect_slashes=False)

    # Same order as Plombery
    app.mount("/ws", asgi, name="socket")
    setup_cors(app)

    app.include_router(pipelines.router, prefix=API_PREFIX)
    app.include_router(pipelines.external_router, prefix=API_PREFIX)
    app.include_router(runs.router, prefix=API_PREFIX)
    app.include_router(tokens.router, prefix=API_PREFIX)
    app.include_router(build_auth_router(app), prefix=API_PREFIX)

    # Add your API BEFORE the SPA catch-all mount
    app.include_router(jobs_router)

    # Keep this LAST
    app.mount("/", SPAStaticFiles(api_prefix=API_PREFIX))

    return app


app = create_app()

if __name__ == "__main__":
    in_docker = os.path.exists("/.dockerenv") or os.getenv("DOCKER_CONTAINER") == "true"
    host = "0.0.0.0" if in_docker else "127.0.0.1"

    uvicorn.run(app, host=host, port=8000, reload=False)