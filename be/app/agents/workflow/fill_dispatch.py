"""Fill 진입점. 실제 fan-out은 graph.py의 conditional_edges가 slot마다 Send로 처리한다.

흐름: fill_dispatch → (slot마다 Send) → slot_filler ×N → fill_aggregator → END
이 노드 자체는 진입 지점 역할만 하는 no-op.
"""
from app.agents.state import RESET, GraphState
from app.core.logging import get_logger

logger = get_logger(__name__)


def fill_dispatch_node(state: GraphState) -> dict:
    template = state.get("template") or {}
    slots = template.get("slots", [])
    n_fill = sum(1 for s in slots if s.get("needs_fill", True))
    logger.info(
        "fill_dispatch: '%s' slot %d개 (채움 %d · 스킵 %d)",
        template.get("name", "?"), len(slots), n_fill, len(slots) - n_fill,
    )
    # 이전 채우기 결과 초기화 (같은 thread에서 재채우기 시 누적 방지)
    return {"filled_slots": RESET}
