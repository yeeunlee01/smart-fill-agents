"""Slot filler: 템플릿 항목 1개를 채운다 (RAG 검색 → 작성).

fill_dispatch가 Send로 slot마다 이 노드를 병렬로 띄운다.
입력 state(=Send 페이로드): {"slot": {name, definition}, "idx": int, "documents": [...]}
출력: {"filled_slots": [채운 결과 1개]}  (operator.add 리듀서로 누적됨)
"""
import asyncio

from app.agents.prompts.fill import SLOT_FILL_SYSTEM_PROMPT
from app.core.logging import get_logger
from app.llm.client import get_llm
from app.rag.retriever import search

logger = get_logger(__name__)


def _format_context(hits: list[dict]) -> str:
    return "\n\n".join(
        f"[{i + 1}] ({h.get('doc')} · {h.get('location')})\n{h.get('text')}"
        for i, h in enumerate(hits)
    )


async def slot_filler_node(state: dict) -> dict:
    slot = state.get("slot") or {}
    idx = state.get("idx", 0)
    documents = state.get("documents") or []
    name = slot.get("name", "")
    definition = slot.get("definition", "")

    # RAG 검색 (블로킹 → 스레드로 빼서 slot들끼리 병렬 유지)
    query = f"{name} {definition}".strip()
    hits = await asyncio.to_thread(search, query, 4, documents or None)

    if not hits:
        content = "(관련 내용을 문서에서 찾지 못했습니다)"
    else:
        llm = get_llm(temperature=0.2)
        resp = await llm.ainvoke(
            [
                {"role": "system", "content": SLOT_FILL_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"항목: {name}\n채울 내용(가이드): {definition}\n\n참고 자료:\n{_format_context(hits)}",
                },
            ]
        )
        content = resp.content

    logger.info("slot_filler: %r → hits=%d", name[:30], len(hits))
    return {
        "filled_slots": [
            {"idx": idx, "name": name, "definition": definition, "content": content, "sources": hits}
        ]
    }
