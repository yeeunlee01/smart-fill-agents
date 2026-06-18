"""검색 로직. agents/tools/retriever.py가 이 함수를 감싼다."""
from app.core.config import settings
from app.rag.embeddings import embed
from app.rag.milvus_client import get_client


def search(query: str, top_k: int = 5) -> list[str]:
    # TODO: 쿼리 임베딩 -> Milvus search -> 텍스트 청크 반환
    client = get_client()  # noqa: F841
    vector = embed([query])[0]  # noqa: F841
    # results = client.search(collection_name=settings.milvus_collection, data=[vector], limit=top_k)
    return []
