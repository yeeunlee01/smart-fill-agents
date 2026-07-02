"""Responder 노드: 작업을 진행할 수 없을 때 안내 메시지만 내고 종료.

supervisor의 결정적 가드(문서 없음 / 템플릿 미선택)에서 넘어온다.
어떤 안내를 낼지는 artifacts['respond_reason']로 구분한다.
"""
from app.agents.state import GraphState

_MESSAGES = {
    "need_docs": "먼저 문서를 첨부해 주세요. 문서를 받아야 채우거나 답변할 수 있어요 📎",
    "need_template": "채울 템플릿을 먼저 선택해 주세요 📄",
}


def responder_node(state: GraphState) -> dict:
    reason = state.get("artifacts", {}).get("respond_reason", "need_docs")
    text = _MESSAGES.get(reason, _MESSAGES["need_docs"])
    # add_messages 리듀서로 assistant 메시지를 대화에 누적
    return {"messages": [{"role": "assistant", "content": text}]}
