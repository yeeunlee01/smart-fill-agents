"""모든 노드가 공유하는 그래프 상태."""
from typing import Annotated, Optional, TypedDict

from langgraph.graph.message import add_messages

# fill 결과 누적 리듀서: 병렬 slot_filler들의 결과를 더하되,
# "__reset__"을 받으면 비운다 (같은 thread에서 재채우기 시 이전 결과 누적 방지).
RESET = "__reset__"


def fill_reducer(current: list, update) -> list:
    if update == RESET:
        return []
    return (current or []) + (update or [])


class GraphState(TypedDict, total=False):
    # 대화 메시지 (add_messages 리듀서로 누적)
    messages: Annotated[list, add_messages]
    # supervisor가 써넣는 다음 행선지 (routes.ROUTE_MAP의 키와 매칭)
    next: str
    # supervisor가 분류한 의도 (Chat | DocQA | TemplateFill | Ask) — 응답/디버깅용
    intent: str
    # 첨부 문서 식별자(파일명 등). Milvus에 적재된 문서를 가리킨다.
    documents: list[str]
    # fill 대상 템플릿 {name, slots:[{name, definition}]} — qa면 None
    template: Optional[dict]
    # 워크플로우 진행 중 산출물 공유 슬롯 (추출 결과, 채워진 slot 등)
    artifacts: dict
    # fill: slot_filler들이 병렬로 채운 결과를 누적 (fill_reducer로 합침/초기화)
    filled_slots: Annotated[list, fill_reducer]
