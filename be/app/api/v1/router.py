"""v1 라우터 집계."""
from fastapi import APIRouter

from app.api.v1.endpoints import chat, documents, health, templates

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(templates.router, prefix="/templates", tags=["templates"])
