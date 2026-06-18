"""모든 노드가 공유하는 그래프 상태."""
from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class GraphState(TypedDict):
    # 대화 메시지 (add_messages 리듀서로 누적)
    messages: Annotated[list, add_messages]
    # supervisor가 써넣는 다음 행선지 (routes.py의 키와 매칭)
    next: str
    # 워크플로우 진행 중 산출물 공유 슬롯 (예: 추출 결과, 채워진 템플릿 등)
    artifacts: dict
