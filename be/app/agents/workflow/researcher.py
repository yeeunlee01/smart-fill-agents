"""Researcher 에이전트: 첨부 문서에서 질문 관련 청크를 RAG로 검색."""
from app.agents.state import GraphState
from app.agents.utils import last_user_text
from app.core.logging import get_logger
from app.rag.retriever import search

logger = get_logger(__name__)


def researcher_node(state: GraphState) -> dict:
    query = last_user_text(state.get("messages", []))
    documents = state.get("documents") or []
    hits = search(query, top_k=5, documents=documents or None)
    logger.info("researcher: query=%r docs=%d → hits=%d", query[:40], len(documents), len(hits))
    return {"artifacts": {**state.get("artifacts", {}), "retrieved": hits}}
