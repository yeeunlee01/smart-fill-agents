"""Supervisor 라우터 노드.

역할은 오직 "다음에 어디로 갈지" 판단해서 state['next']에 써넣는 것.
실제 분기는 graph.py의 conditional_edges가 routes.ROUTE_MAP을 보고 처리한다.

판단 순서:
  1) LLM 의도 분류 — Chat / DocQA / TemplateFill (구조화 출력)
  2) Chat → 문서 없이도 응답 (잡담/안내)
  3) DocQA / TemplateFill → 문서 필요. 없으면 Ask(need_docs)
     TemplateFill 은 추가로 템플릿 필요. 없으면 Ask(need_template)
"""
from typing import Literal

from pydantic import BaseModel, Field

from app.agents.prompts.supervisor import SUPERVISOR_SYSTEM_PROMPT
from app.agents.state import GraphState
from app.agents.utils import last_user_text
from app.core.logging import get_logger
from app.llm.client import get_llm

logger = get_logger(__name__)


class RouteDecision(BaseModel):
    """supervisor의 의도 분류 결과 (구조화 출력)."""

    intent: Literal["Chat", "DocQA", "TemplateFill"] = Field(description="사용자 마지막 발화의 의도")


def _ask(state: GraphState, reason: str) -> dict:
    """Ask 경로로 보낸다. responder가 reason에 맞는 안내 메시지를 낸다."""
    return {
        "next": "Ask",
        "intent": "Ask",
        "artifacts": {**state.get("artifacts", {}), "respond_reason": reason},
    }


async def supervisor_node(state: GraphState) -> dict:
    text = last_user_text(state.get("messages", []))
    documents = state.get("documents") or []
    template = state.get("template")

    # 1) LLM 의도 분류 — 첨부/템플릿 상태를 함께 주어 정확도를 높인다
    #    (문서가 있고 내용 질문이면 DocQA로 판단되도록)
    ctx = (
        f"[상태] 첨부 문서: {f'있음({len(documents)}개)' if documents else '없음'} / "
        f"선택 템플릿: {template['name'] if template else '없음'}"
    )
    llm = get_llm().with_structured_output(RouteDecision)
    decision: RouteDecision = await llm.ainvoke(
        [
            {"role": "system", "content": SUPERVISOR_SYSTEM_PROMPT},
            {"role": "user", "content": f"{ctx}\n사용자 발화: {text}"},
        ]
    )
    intent = decision.intent
    logger.info("supervisor → %s (docs=%d, template=%s)", intent, len(documents), bool(template))

    # 2) Chat: 문서 없이도 응답 가능
    if intent == "Chat":
        return {"next": "Chat", "intent": "Chat"}

    # 3) DocQA / TemplateFill: 문서가 있어야 한다
    if not documents:
        return _ask(state, "need_docs")

    # TemplateFill: 템플릿도 선택되어 있어야 한다
    if intent == "TemplateFill" and not template:
        return _ask(state, "need_template")

    return {"next": intent, "intent": intent}
