"""에이전트 노드 공용 헬퍼."""


def last_user_text(messages: list) -> str:
    """messages에서 가장 최근 사용자 발화 텍스트를 추출.

    dict({"role"/"content"}) 와 LangChain Message 객체를 모두 지원한다.
    """
    for m in reversed(messages or []):
        role = getattr(m, "type", None) or (m.get("role") if isinstance(m, dict) else None)
        if role in ("human", "user"):
            return getattr(m, "content", None) or (m.get("content", "") if isinstance(m, dict) else "")
    return ""
