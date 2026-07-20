"""Writer 에이전트.

- DocQA 경로: researcher가 모은 근거로 사용자 질문에 답변 작성 (+ 출처 표시)
- TemplateFill 경로: 추출 정보 + slot 정의 → slot 내용 작성 (fill 단계에서 확장)
"""
from app.agents.prompts.writer import DOCQA_SYSTEM_PROMPT
from app.agents.state import GraphState
from app.agents.utils import extract_evidence, last_user_text, to_llm_messages
from app.llm.client import get_llm


def _format_sources(hits: list[dict]) -> str:
    seen, lines = set(), []
    for h in hits:
        key = (h.get("doc"), h.get("location"))
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- **{h.get('doc')}** · {h.get('location')} · 유사도 `{h.get('score')}`")
    return "\n".join(lines)


async def writer_node(state: GraphState) -> dict:
    messages = state.get("messages", [])
    query = last_user_text(messages)
    hits = state.get("artifacts", {}).get("retrieved", [])

    if not hits:
        return {
            "messages": [
                {
                    "role": "assistant",
                    "content": "첨부한 문서에서 관련 내용을 찾지 못했어요. 질문을 바꾸거나 다른 문서를 첨부해 주세요.",
                }
            ]
        }

    # LLM에는 출처(파일명·페이지)를 노출하지 않는다 — 보여주면 그 형식을 본문에 그대로 베껴
    # "출처: [1] (파일 · 페이지)"처럼 답변에 인용이 새어 나온다. 근거는 아래 _format_sources로만.
    context = "\n\n".join(f"자료 {i + 1}:\n{h['text']}" for i, h in enumerate(hits))

    # 직전까지의 대화 히스토리 (후속 질문 문맥용). 마지막 발화(=이번 질문)는 아래에서
    # 참고 자료와 함께 별도로 붙이므로 제외한다. 이전 답변의 '📎 근거' 꼬리는 떼어
    # 그 출처 형식이 새 답변에 베껴 나오는 것을 막는다.
    history = to_llm_messages(messages[:-1])
    for m in history:
        if m["role"] == "assistant":
            m["content"] = m["content"].split("\n\n---\n📎")[0].rstrip()

    llm = get_llm(streaming=True)
    resp = await llm.ainvoke(
        [
            {"role": "system", "content": DOCQA_SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": f"질문: {query}\n\n참고 자료:\n{context}"},
        ]
    )
    answer = resp.content
    reply = f"{answer}\n\n---\n📎 **근거**\n{_format_sources(hits)}"
    # 답변의 근거 문장을 뽑아 하이라이트 타깃으로 (검증 통과분만) → artifacts로 chat_service에 전달
    evidence = await extract_evidence(answer, context, hits)
    return {
        "messages": [{"role": "assistant", "content": reply}],
        "artifacts": {**state.get("artifacts", {}), "evidence": evidence},
    }
