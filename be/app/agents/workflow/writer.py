"""Writer 에이전트.

- DocQA 경로: researcher가 모은 근거로 사용자 질문에 답변 작성 (+ 출처 표시)
- TemplateFill 경로: 추출 정보 + slot 정의 → slot 내용 작성 (fill 단계에서 확장)
"""
from pydantic import BaseModel, Field

from app.agents.prompts.writer import DOCQA_SYSTEM_PROMPT, EVIDENCE_EXTRACT_PROMPT
from app.agents.state import GraphState
from app.agents.utils import last_user_text
from app.core.logging import get_logger
from app.llm.client import get_llm

logger = get_logger(__name__)


class _Evidence(BaseModel):
    quotes: list[str] = Field(
        default_factory=list,
        description="답변의 근거가 된 문장을 참고 자료에서 그대로 발췌 (최대 3개, 없으면 빈 리스트)",
    )


def _norm(s: str) -> str:
    return " ".join((s or "").split()).lower()


async def _extract_evidence(answer: str, context: str, hits: list[dict]) -> list[dict]:
    """답변의 근거 문장을 참고 자료에서 원문 그대로 뽑아 (doc, location)에 매핑.

    LLM이 발췌한 문장이 실제 청크에 있는지 substring으로 '검증'해서 통과한 것만 반환.
    → 하이라이트 타깃(문장 단위). 검증 실패(의역 등)는 버린다.
    """
    llm = get_llm().with_structured_output(_Evidence)
    try:
        result: _Evidence = await llm.ainvoke(
            [
                {"role": "system", "content": EVIDENCE_EXTRACT_PROMPT},
                {"role": "user", "content": f"답변:\n{answer}\n\n참고 자료:\n{context}"},
            ]
        )
    except Exception as e:  # noqa: BLE001 — 근거 추출 실패해도 답변엔 영향 없음
        logger.warning("evidence 추출 실패: %s", e)
        return []

    evidence: list[dict] = []
    for q in result.quotes:
        nq = _norm(q)
        if not nq:
            continue
        hit = next((h for h in hits if nq in _norm(h.get("text", ""))), None)
        if hit is not None:  # 실제 청크에 있는 문장인지 검증
            evidence.append({"doc": hit.get("doc"), "location": hit.get("location"), "quote": q.strip()})
    logger.info("evidence: 발췌 %d개 → 검증통과 %d개", len(result.quotes), len(evidence))
    return evidence


def _format_sources(hits: list[dict]) -> str:
    seen, lines = set(), []
    for h in hits:
        key = (h.get("doc"), h.get("location"))
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- **{h.get('doc')}** · {h.get('location')} · 유사도 `{h.get('score')}`")
    return "\n".join(lines)


async def writer_node(state: GraphState) -> dict:
    query = last_user_text(state.get("messages", []))
    hits = state.get("artifacts", {}).get("retrieved", [])

    if not hits:
        return {
            "messages": [
                {
                    "role": "assistant",
                    "content": "첨부한 문서에서 관련 내용을 찾지 못했어요. 질문을 바꾸거나 다른 문서를 첨부해 주세요.",
                }
            ]
        }

    # LLM에는 출처(파일명·페이지)를 노출하지 않는다 — 보여주면 그 형식을 본문에 그대로 베껴
    # "출처: [1] (파일 · 페이지)"처럼 답변에 인용이 새어 나온다. 근거는 아래 _format_sources로만.
    context = "\n\n".join(f"자료 {i + 1}:\n{h['text']}" for i, h in enumerate(hits))
    llm = get_llm(streaming=True)
    resp = await llm.ainvoke(
        [
            {"role": "system", "content": DOCQA_SYSTEM_PROMPT},
            {"role": "user", "content": f"질문: {query}\n\n참고 자료:\n{context}"},
        ]
    )
    answer = resp.content
    reply = f"{answer}\n\n---\n📎 **근거**\n{_format_sources(hits)}"
    # 답변의 근거 문장을 뽑아 하이라이트 타깃으로 (검증 통과분만) → artifacts로 chat_service에 전달
    evidence = await _extract_evidence(answer, context, hits)
    return {
        "messages": [{"role": "assistant", "content": reply}],
        "artifacts": {**state.get("artifacts", {}), "evidence": evidence},
    }
