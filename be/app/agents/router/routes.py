"""라우팅 테이블: supervisor의 판단(next) -> 실제 노드 이름.

supervisor가 state["next"]에 아래 키 중 하나를 써넣으면,
graph.py의 conditional_edges가 이 매핑을 보고 해당 노드로 분기한다.
"""
from langgraph.graph import END

# 노드 이름 상수 (graph.py의 add_node 이름과 일치시킬 것)
SUPERVISOR = "supervisor"
RESEARCHER = "researcher"
WRITER = "writer"
REVIEWER = "reviewer"

# supervisor 판단 -> 분기 대상
ROUTE_MAP = {
    "research": RESEARCHER,
    "write": WRITER,
    "review": REVIEWER,
    "done": END,
}
