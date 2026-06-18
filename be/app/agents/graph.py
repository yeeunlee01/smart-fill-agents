"""전체 워크플로우 조립 (지도 역할).

구조: 각 작업 에이전트가 일을 마치면 supervisor로 복귀 -> supervisor가 다음 행선지 결정.
(일부 구간을 고정 엣지로 직결하려면 add_edge로 바꾸면 됨.)
"""
from langgraph.graph import StateGraph, START

from app.agents.state import GraphState
from app.agents.router.supervisor import supervisor_node
from app.agents.router import routes
from app.agents.workflow.researcher import researcher_node
from app.agents.workflow.writer import writer_node
from app.agents.workflow.reviewer import reviewer_node


def build_graph(checkpointer=None):
    g = StateGraph(GraphState)

    # 노드 등록
    g.add_node(routes.SUPERVISOR, supervisor_node)
    g.add_node(routes.RESEARCHER, researcher_node)
    g.add_node(routes.WRITER, writer_node)
    g.add_node(routes.REVIEWER, reviewer_node)

    # 진입점 -> supervisor
    g.add_edge(START, routes.SUPERVISOR)

    # supervisor 판단(next) -> 분기 (routes.ROUTE_MAP 사용)
    g.add_conditional_edges(
        routes.SUPERVISOR,
        lambda state: state["next"],
        routes.ROUTE_MAP,
    )

    # 작업 에이전트는 끝나면 supervisor로 복귀 (중앙 라우팅)
    g.add_edge(routes.RESEARCHER, routes.SUPERVISOR)
    g.add_edge(routes.WRITER, routes.SUPERVISOR)
    g.add_edge(routes.REVIEWER, routes.SUPERVISOR)

    return g.compile(checkpointer=checkpointer)
