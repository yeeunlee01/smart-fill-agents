"""Milvus 연결/컬렉션 관리."""
from functools import lru_cache

from pymilvus import MilvusClient

from app.core.config import settings


@lru_cache
def get_client() -> MilvusClient:
    return MilvusClient(uri=f"http://{settings.milvus_host}:{settings.milvus_port}")
