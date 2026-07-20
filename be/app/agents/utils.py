"""에이전트 노드 공용 헬퍼."""
import asyncio
import re

from pydantic import BaseModel, Field

from app.agents.prompts.writer import EVIDENCE_EXTRACT_PROMPT
from app.core.logging import get_logger
from app.llm.client import get_llm

logger = get_logger(__name__)

# 프론트 하이라이트 매칭과 동일한 규칙: 한글·영숫자만 남기고 공백·기호·구두점 전부 무시.
# → LLM 발췌가 원문과 기호(| , 등)만 달라도 검증을 통과시킨다.
_SIG_RE = re.compile(r"[^0-9a-z가-힣]")


def _sig(s: str) -> str:
    return _SIG_RE.sub("", (s or "").lower())


def last_user_text(messages: list) -> str:
    """messages에서 가장 최근 사용자 발화 텍스트를 추출.

    dict({"role"/"content"}) 와 LangChain Message 객체를 모두 지원한다.
    """
    for m in reversed(messages or []):
        role = getattr(m, "type", None) or (m.get("role") if isinstance(m, dict) else None)
        if role in ("human", "user"):
            return getattr(m, "content", None) or (m.get("content", "") if isinstance(m, dict) else "")
    return ""


# LangChain Message.type → OpenAI 형식 role 매핑
_ROLE_MAP = {"human": "user", "ai": "assistant"}


def to_llm_messages(messages: list, limit: int = 20) -> list[dict]:
    """누적된 대화 state를 LLM 입력용 [{role, content}] 리스트로 변환 (멀티턴 문맥).

    - user/assistant 발화만 남긴다 (system은 각 노드가 앞에 직접 붙인다)
    - 최근 limit개만 잘라 토큰/비용 폭증을 막는다 (슬라이딩 윈도우)
    dict 와 LangChain Message 객체를 모두 지원한다 (last_user_text와 동일 규칙).
    """
    out: list[dict] = []
    for m in (messages or [])[-limit:]:
        role = getattr(m, "type", None) or (m.get("role") if isinstance(m, dict) else None)
        role = _ROLE_MAP.get(role, role)
        content = getattr(m, "content", None) or (m.get("content", "") if isinstance(m, dict) else "")
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content})
    return out


class _Evidence(BaseModel):
    quotes: list[str] = Field(
        default_factory=list,
        description="근거가 된 문장을 참고 자료에서 그대로, 빠짐없이 모두 발췌 (개수 제한 없음, 없으면 빈 리스트)",
    )


def _is_rate_limit(e: Exception) -> bool:
    s = str(e)
    return "429" in s or "rate_limit" in s or "rate limit" in s.lower()


async def extract_evidence(answer: str, context: str, hits: list[dict]) -> list[dict]:
    """작성된 내용(answer)의 근거 문장을 참고 자료에서 원문 그대로 뽑아 (doc, location)에 매핑.

    LLM 발췌가 실제 청크에 있는지 substring으로 '검증'해서 통과분만 반환.
    → 하이라이트 타깃(문장 단위). DocQA(writer)·템플릿채우기(slot_filler) 공용.

    slot 병렬 채움 직후 호출되어 TPM(분당 토큰) 한도에 걸리기 쉬움 → 429는 백오프 재시도.
    """
    llm = get_llm().with_structured_output(_Evidence)
    messages = [
        {"role": "system", "content": EVIDENCE_EXTRACT_PROMPT},
        {"role": "user", "content": f"작성된 내용:\n{answer}\n\n참고 자료:\n{context}"},
    ]
    max_attempts = 4
    result: _Evidence | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = await llm.ainvoke(messages)
            break
        except Exception as e:  # noqa: BLE001 — 근거 추출 실패해도 본문엔 영향 없음
            if _is_rate_limit(e) and attempt < max_attempts:
                delay = 10 * attempt  # 10s → 20s → 30s (TPM은 분 단위로 회복)
                logger.info("evidence 추출 rate limit (시도 %d/%d) → %ds 후 재시도", attempt, max_attempts, delay)
                await asyncio.sleep(delay)
                continue
            logger.warning("evidence 추출 실패: %s", e)
            return []
    if result is None:
        return []

    evidence: list[dict] = []
    for q in result.quotes:
        sq = _sig(q)
        if len(sq) < 4:  # 너무 짧은 발췌는 오검증 방지로 제외
            continue
        hit = next((h for h in hits if sq in _sig(h.get("text", ""))), None)
        if hit is not None:  # 실제 청크에 있는 문장인지 검증 (기호·공백 무시)
            evidence.append({"doc": hit.get("doc"), "location": hit.get("location"), "quote": q.strip()})
    logger.info("evidence: 발췌 %d개 → 검증통과 %d개", len(result.quotes), len(evidence))
    return evidence
