"""LLM/임베딩 호출용 httpx 클라이언트.

사내 게이트웨이가 자기서명 CA(SK holdings C&C)를 쓰므로, 해당 CA 번들이 있으면
그걸로 TLS 검증한다. 파일이 없으면 기본 시스템 CA로 폴백.
"""
import os

import httpx

from app.core.config import settings


def _verify():
    ca = settings.openai_ca_bundle
    return ca if ca and os.path.exists(ca) else True


def sync_client() -> httpx.Client:
    return httpx.Client(verify=_verify())


def async_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(verify=_verify())
