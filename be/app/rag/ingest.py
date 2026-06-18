"""문서 적재 파이프라인: 파싱 -> 청킹 -> 임베딩 -> Milvus upsert."""
from app.core.config import settings
from app.rag.embeddings import embed
from app.rag.milvus_client import get_client


def ingest_documents(chunks: list[str]) -> int:
    # TODO: chunks 임베딩 후 Milvus에 upsert. 적재 건수 반환
    client = get_client()  # noqa: F841
    vectors = embed(chunks)  # noqa: F841
    # client.insert(collection_name=settings.milvus_collection, data=...)
    return len(chunks)
