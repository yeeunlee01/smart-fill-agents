"""Chat 노드: 문서가 필요 없는 잡담·안내성 발화에 응답.

supervisor가 intent=chat 으로 분류했을 때 진입한다.
일반 지식/문서 질문은 추측하지 않고 서비스 사용을 유도하도록 프롬프트로 제약한다.
"""
from app.agents.prompts.chat import CHAT_SYSTEM_PROMPT
from app.agents.state import GraphState
from app.agents.utils import last_user_text
from app.llm.client import get_llm


async def chat_node(state: GraphState) -> dict:
    text = last_user_text(state.get("messages", []))
    llm = get_llm(temperature=0.5, streaming=True)
    resp = await llm.ainvoke(
        [
            {"role": "system", "content": CHAT_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ]
    )
    return {"messages": [{"role": "assistant", "content": resp.content}]}
