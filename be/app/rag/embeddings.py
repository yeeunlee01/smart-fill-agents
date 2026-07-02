"""임베딩 생성. MODE=personal → 개인 OpenAI(api.openai.com), 그 외 → 사내 Azure 게이트웨이."""
from langchain_openai import AzureOpenAIEmbeddings, OpenAIEmbeddings

from app.core.config import settings
from app.llm.http import async_client, sync_client


def get_embedder():
    if settings.is_personal:
        return OpenAIEmbeddings(
            model=settings.openai_embedding_model,
            api_key=settings.openai_api_key_personal,
        )
    return AzureOpenAIEmbeddings(
        azure_endpoint=settings.azure_openai_endpoint,
        azure_deployment=settings.openai_embedding_model,
        api_version=settings.openai_api_version,
        api_key=settings.openai_api_key,
        http_client=sync_client(),
        http_async_client=async_client(),
    )


def embed(texts: list[str]) -> list[list[float]]:
    return get_embedder().embed_documents(texts)
