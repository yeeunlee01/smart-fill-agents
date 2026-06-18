"""Writer 에이전트: 추출 정보를 템플릿에 맞게 채워 산출물 생성."""
from app.agents.state import GraphState


def writer_node(state: GraphState) -> dict:
    # TODO: artifacts의 추출 정보 + 템플릿 -> 채워진 결과 생성 (LLM 호출)
    return {"artifacts": {**state.get("artifacts", {})}}
