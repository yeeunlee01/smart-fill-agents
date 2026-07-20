"""Fill aggregator: 병렬로 채운 slot들을 원문 순서대로 모아 결과 문서를 만든다."""
from app.agents.state import GraphState


def _format_sources(filled: list[dict]) -> str:
    seen, lines = set(), []
    for s in filled:
        for h in s.get("sources", []):
            key = (h.get("doc"), h.get("location"))
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"- **{h.get('doc')}** · {h.get('location')} · 유사도 `{h.get('score')}`")
    return "\n".join(lines)


def fill_aggregator_node(state: GraphState) -> dict:
    template = state.get("template") or {}
    name = template.get("name", "템플릿")
    filled = sorted(state.get("filled_slots") or [], key=lambda s: s.get("idx", 0))
    # 제목·라벨 등 스킵된 slot은 결과 본문에서 제외
    written = [s for s in filled if not s.get("skipped") and (s.get("content") or "").strip()]

    if not written:
        return {
            "messages": [
                {"role": "assistant", "content": f"'{name}'에 채울 항목이 없어요. 템플릿에 항목을 추가해 주세요."}
            ]
        }

    # 원문 순서대로 '항목명 + 채운 내용' 재조립 (원문 구조 보존)
    body = "\n\n".join(f"**{s['name']}**\n{s['content']}" for s in written)
    sources = _format_sources(written)
    reply = f"📄 **{name}** 채우기 완료\n\n{body}"
    if sources:
        reply += f"\n\n---\n📎 **근거**\n{sources}"

    return {"messages": [{"role": "assistant", "content": reply}]}
