"""FastAPI 진입점."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.logging import setup_logging
from app.memory.checkpointer import close_checkpointer, init_checkpointer

# 프론트엔드(바닐라 HTML/JS) 정적 파일 위치
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작: checkpointer(async Postgres) 풀 오픈 + 테이블 생성
    await init_checkpointer()
    yield
    # 종료: 풀 정리
    await close_checkpointer()


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title="smart-fill-agents", lifespan=lifespan)
    app.include_router(api_router, prefix="/api/v1")
    # API 라우터 다음에 마운트 → /api/v1/* 가 우선 매칭되고, 나머지는 정적 파일/SPA
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


app = create_app()
