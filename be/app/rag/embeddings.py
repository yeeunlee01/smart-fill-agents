"""임베딩 생성."""
from langchain_openai import OpenAIEmbeddings

from app.core.config import settings


def get_embedder() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        api_key=settings.openai_api_key,
    )


def embed(texts: list[str]) -> list[list[float]]:
    return get_embedder().embed_documents(texts)
