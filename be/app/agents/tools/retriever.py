"""에이전트용 검색 툴. 실제 검색 로직은 rag 레이어를 감싸기만 한다 (재사용성)."""
from langchain_core.tools import tool

from app.rag.retriever import search


@tool
def retrieve(query: str, top_k: int = 5, documents: list[str] | None = None) -> list[dict]:
    """주어진 query로 Milvus에서 관련 문서 청크를 검색한다 (근거 포함)."""
    return search(query, top_k=top_k, documents=documents)
