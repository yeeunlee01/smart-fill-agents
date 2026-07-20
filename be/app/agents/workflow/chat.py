"""Chat 노드: 문서가 필요 없는 잡담·안내성 발화에 응답.

supervisor가 intent=chat 으로 분류했을 때 진입한다.
일반 지식/문서 질문은 추측하지 않고 서비스 사용을 유도하도록 프롬프트로 제약한다.
"""
from app.agents.prompts.chat import CHAT_SYSTEM_PROMPT
from app.agents.state import GraphState
from app.agents.utils import to_llm_messages
from app.llm.client import get_llm


async def chat_node(state: GraphState) -> dict:
    # 최근 대화 히스토리를 통째로 넘겨 멀티턴 문맥을 유지 (마지막 발화 = 이번 질문)
    history = to_llm_messages(state.get("messages", []))
    llm = get_llm(temperature=0.5, streaming=True)
    resp = await llm.ainvoke(
        [{"role": "system", "content": CHAT_SYSTEM_PROMPT}, *history]
    )
    return {"messages": [{"role": "assistant", "content": resp.content}]}
