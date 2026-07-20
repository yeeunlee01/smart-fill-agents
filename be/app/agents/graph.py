"""전체 워크플로우 조립 (지도 역할).

구조: supervisor가 진입 시 의도를 분류해 경로를 정한다.
    START → supervisor ─┬─ Chat         → chat                       → END
                        ├─ DocQA        → researcher → writer        → END
                        ├─ TemplateFill → fill_dispatch ─(Send)→ ...  → END
                        └─ Ask          → responder                  → END
"""
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.agents.router import routes
from app.agents.router.supervisor import supervisor_node
from app.agents.state import GraphState
from app.agents.workflow.chat import chat_node
from app.agents.workflow.fill_aggregator import fill_aggregator_node
from app.agents.workflow.fill_dispatch import fill_dispatch_node
from app.agents.workflow.researcher import researcher_node
from app.agents.workflow.responder import responder_node
from app.agents.workflow.slot_filler import slot_filler_node
from app.agents.workflow.writer import writer_node
from app.core.logging import get_logger

logger = get_logger(__name__)


def _fan_out_slots(state: GraphState):
    """fill_dispatch 이후: 템플릿 slot마다 slot_filler를 Send로 병렬 실행.

    needs_fill=False(제목·라벨 등)인 slot도 Send는 하되, slot_filler가 LLM 없이 즉시 스킵한다.
    → filled_slots의 idx가 템플릿 slot 순서와 맞게 유지된다.
    """
    template = state.get("template") or {}
    slots = template.get("slots", [])
    documents = state.get("documents") or []
    if not slots:
        return routes.FILL_AGGREGATOR  # 채울 항목 없음 → 바로 집계(안내)
    n_fill = sum(1 for s in slots if s.get("needs_fill", True))
    logger.info("fill fan-out: %d slots (%d to fill, %d skip)", len(slots), n_fill, len(slots) - n_fill)
    return [
        Send(routes.SLOT_FILLER, {"slot": s, "idx": i, "documents": documents})
        for i, s in enumerate(slots)
    ]


def build_graph(checkpointer=None):
    g = StateGraph(GraphState)

    # 노드 등록
    g.add_node(routes.SUPERVISOR, supervisor_node)
    g.add_node(routes.CHAT, chat_node)
    g.add_node(routes.RESPONDER, responder_node)
    g.add_node(routes.RESEARCHER, researcher_node)
    g.add_node(routes.WRITER, writer_node)
    g.add_node(routes.FILL_DISPATCH, fill_dispatch_node)
    g.add_node(routes.SLOT_FILLER, slot_filler_node)
    g.add_node(routes.FILL_AGGREGATOR, fill_aggregator_node)

    # 진입점 -> supervisor
    g.add_edge(START, routes.SUPERVISOR)

    # supervisor 의도(next) -> 경로 분기 (routes.ROUTE_MAP)
    g.add_conditional_edges(
        routes.SUPERVISOR,
        lambda state: state["next"],
        routes.ROUTE_MAP,
    )

    # chat 경로: 안내/잡담 응답 후 종료
    g.add_edge(routes.CHAT, END)

    # respond 경로: 안내 후 종료
    g.add_edge(routes.RESPONDER, END)

    # DocQA 경로: 검색 → 답변 → 종료
    g.add_edge(routes.RESEARCHER, routes.WRITER)
    g.add_edge(routes.WRITER, END)

    # fill 경로: 디스패처 → (slot마다 Send) → slot_filler ×N → aggregator → 종료
    g.add_conditional_edges(routes.FILL_DISPATCH, _fan_out_slots, [routes.SLOT_FILLER, routes.FILL_AGGREGATOR])
    g.add_edge(routes.SLOT_FILLER, routes.FILL_AGGREGATOR)
    g.add_edge(routes.FILL_AGGREGATOR, END)

    return g.compile(checkpointer=checkpointer)
