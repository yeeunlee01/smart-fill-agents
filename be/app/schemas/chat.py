"""API 요청/응답 모델 (도메인/그래프 state와 분리)."""
from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None  # 멀티턴 대화 식별 (checkpointer용)


class ChatResponse(BaseModel):
    reply: str
    thread_id: str
