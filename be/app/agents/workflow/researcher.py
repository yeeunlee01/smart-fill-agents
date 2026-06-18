"""Researcher 에이전트: 입력 문서/지식 검색 및 정보 추출."""
from app.agents.state import GraphState


def researcher_node(state: GraphState) -> dict:
    # TODO: tools.retriever로 Milvus 검색 -> 필요한 정보 추출
    #   결과를 state['artifacts']에 적재
    return {"artifacts": {**state.get("artifacts", {})}}
