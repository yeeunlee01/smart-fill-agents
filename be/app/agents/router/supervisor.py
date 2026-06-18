"""Supervisor 라우터 노드.

역할은 오직 "다음에 어디로 갈지" 판단해서 state['next']에 써넣는 것.
실제 분기는 graph.py의 conditional_edges가 routes.ROUTE_MAP을 보고 처리한다.
"""
from app.agents.state import GraphState
from app.agents.prompts.supervisor import SUPERVISOR_SYSTEM_PROMPT  # noqa: F401


def supervisor_node(state: GraphState) -> dict:
    # TODO: LLM에게 현재 messages/artifacts를 주고 다음 액션을 결정시킨다.
    #   - 구조화 출력(예: {"next": "research"})으로 받기
    #   - SUPERVISOR_SYSTEM_PROMPT 활용
    # 지금은 스텁: 곧장 종료
    return {"next": "done"}
