"""API 요청/응답 모델 (도메인/그래프 state와 분리)."""
from pydantic import BaseModel, Field


class TemplateSlot(BaseModel):
    name: str
    definition: str = ""


class TemplatePayload(BaseModel):
    """fill 대상 템플릿. qa 요청이면 생략(None)."""

    name: str
    slots: list[TemplateSlot] = Field(default_factory=list)


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None  # 멀티턴 대화 식별 (checkpointer용)
    documents: list[str] = Field(default_factory=list)  # 첨부 문서 식별자(파일명)
    template: TemplatePayload | None = None  # fill 대상 (미선택이면 None)


class ChatResponse(BaseModel):
    reply: str
    thread_id: str
    intent: str | None = None  # supervisor 분류 결과 (Chat | DocQA | TemplateFill | Ask)
