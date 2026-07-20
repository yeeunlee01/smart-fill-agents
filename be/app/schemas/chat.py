"""API 요청/응답 모델 (도메인/그래프 state와 분리)."""
from pydantic import BaseModel, Field


class SlotLayout(BaseModel):
    """이 slot이 문서에서 어떤 형식인지 (구조 인식 채우기용). 프론트가 템플릿 구조에서 계산."""

    type: str = "text"                              # "text" | "table" | "list" | "box"(1칸 문단 작성란)
    orientation: str = ""                           # 표 방향: "row"(아래로) | "col"(오른쪽) | "kv"(항목-값 양식)
    fields: list[str] = Field(default_factory=list)  # 표: 고정 필드명(행방향=열헤더, 열방향=행라벨)
    blanks: list[str] = Field(default_factory=list)  # 텍스트: 채울 빈칸의 안내 텍스트("○○○ 주식회사" 등)
    repeatable: bool = False                        # 목록/표: 항목·행을 내용에 따라 늘릴 수 있는지


class TemplateSlot(BaseModel):
    name: str
    definition: str = ""
    layout: SlotLayout | None = None
    # False면 제목·라벨 등 채울 칸이 없는 slot → slot_filler가 LLM/RAG 없이 건너뜀
    needs_fill: bool = True
    # detect_regions 결과. 빈 배열이면 채울 자리 없음(이중 가드). 없으면 미전송.
    regions: list | None = None


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
