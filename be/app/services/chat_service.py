"""api <-> agents 연결. 그래프 컴파일/실행 오케스트레이션."""
import uuid

from app.agents.graph import build_graph
from app.memory.checkpointer import get_checkpointer
from app.schemas.chat import ChatRequest, ChatResponse


class ChatService:
    def __init__(self) -> None:
        # checkpointer 주입해 멀티턴 대화 지속
        self.graph = build_graph(checkpointer=get_checkpointer())

    async def run(self, req: ChatRequest) -> ChatResponse:
        thread_id = req.thread_id or str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        result = await self.graph.ainvoke(
            {"messages": [{"role": "user", "content": req.message}], "artifacts": {}},
            config=config,
        )

        # TODO: result에서 최종 응답 추출 (마지막 assistant 메시지 등)
        reply = result["messages"][-1].content if result.get("messages") else ""
        return ChatResponse(reply=reply, thread_id=thread_id)
