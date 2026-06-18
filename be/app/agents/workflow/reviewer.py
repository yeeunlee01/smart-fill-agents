"""Reviewer 에이전트: 채워진 산출물 검수/수정 제안."""
from app.agents.state import GraphState


def reviewer_node(state: GraphState) -> dict:
    # TODO: writer 산출물 검증 (누락/오류 체크). 문제 있으면 재작업 유도
    return {"artifacts": {**state.get("artifacts", {})}}
