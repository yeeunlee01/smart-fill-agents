"""LLM 클라이언트 래퍼. 모델/엔드포인트 설정을 한 곳에서 관리.

사내 게이트웨이가 Azure OpenAI 형식(/openai/deployments/{deployment}/chat/completions,
api-version, api-key 헤더)이라 AzureChatOpenAI를 사용한다.
"""
from functools import lru_cache

from langchain_openai import AzureChatOpenAI, ChatOpenAI

from app.core.config import settings
from app.llm.http import async_client, sync_client


@lru_cache
def get_llm(temperature: float = 0.0, streaming: bool = False):
    """streaming=True면 stream 요청 → 토큰을 실시간으로 흘린다.
    (사용자 응답 노드 chat/writer에서만 사용. 구조화 출력 supervisor는 False 유지.)

    모드:
    - MODE=personal: 개인 OpenAI 계정(api.openai.com) 직접 호출 (표준 ChatOpenAI, 시스템 CA).
    - 그 외/미설정(기본): 사내 Azure 형식 게이트웨이(skax). 자기서명 CA 번들 사용.

    참고: 게이트웨이(AI TalentLab)가 Responsible AI 콘텐츠 필터로 응답을 버퍼링해
    실제 토큰 단위 실시간 스트리밍은 안 된다(서버측 asynchronous_filter 설정 필요).
    """
    if settings.is_personal:
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key_personal,
            temperature=temperature,
            streaming=streaming,
        )
    return AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        azure_deployment=settings.openai_model,
        api_version=settings.openai_api_version,
        api_key=settings.openai_api_key,
        temperature=temperature,
        streaming=streaming,
        http_client=sync_client(),
        http_async_client=async_client(),
    )
