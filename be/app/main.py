"""FastAPI 진입점."""
from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.logging import setup_logging


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title="smart-fill-agents")
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
