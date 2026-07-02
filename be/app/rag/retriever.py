"""검색 로직. agents가 이 함수를 호출한다.

반환: 근거 표시까지 담은 dict 리스트
    [{"text": 청크본문, "doc": 파일명, "location": 위치, "score": 유사도}, ...]
"""
from app.core.config import settings
from app.rag.embeddings import embed
from app.rag.milvus_client import get_client


def search(query: str, top_k: int = 5, documents: list[str] | None = None) -> list[dict]:
    """query로 Milvus를 검색. documents가 주어지면 해당 문서들로 범위를 제한한다."""
    client = get_client()
    if not client.has_collection(settings.milvus_collection):
        return []

    vector = embed([query])[0]
    flt = ""
    if documents:
        docs = ", ".join(f'"{d}"' for d in documents)
        flt = f"doc in [{docs}]"

    results = client.search(
        collection_name=settings.milvus_collection,
        data=[vector],
        limit=top_k,
        filter=flt,
        output_fields=["text", "doc", "location"],
    )
    hits = results[0] if results else []
    out = []
    for h in hits:
        ent = h.get("entity", {})
        out.append(
            {
                "text": ent.get("text", ""),
                "doc": ent.get("doc", ""),
                "location": ent.get("location", ""),
                "score": round(float(h.get("distance", 0.0)), 3),
            }
        )
    return out
