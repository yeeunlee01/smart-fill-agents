"""api <-> agents 연결. 그래프 컴파일/실행 오케스트레이션."""
import uuid
from typing import AsyncIterator

from app.agents.graph import build_graph
from app.memory.checkpointer import get_checkpointer
from app.schemas.chat import ChatRequest, ChatResponse

# 토큰을 실시간으로 흘려보낼 사용자 노출 노드 (router/supervisor 내부 호출은 제외)
_STREAMING_NODES = {"chat", "writer"}


def _collect_sources(hits: list[dict], evidence: list[dict] | None = None) -> list[dict]:
    """검색된 청크를 (doc, location) 단위로 묶어 프론트 하이라이트용 구조로 변환.

    texts = 하이라이트할 원문. 우선순위:
      1) writer가 뽑은 '근거 문장'(evidence)이 있으면 그 문장들 → 문장 단위 하이라이트
      2) 없으면 청크 전체 텍스트 → 페이지(청크) 단위 하이라이트 (폴백)
    """
    ev_by_key: dict[tuple, list[str]] = {}
    for e in evidence or []:
        ev_by_key.setdefault((e.get("doc"), e.get("location")), []).append(e.get("quote", ""))

    groups: dict[tuple, dict] = {}
    for h in hits:
        key = (h.get("doc"), h.get("location"))
        g = groups.get(key)
        if g is None:
            g = {"doc": h.get("doc"), "location": h.get("location"), "score": h.get("score"), "texts": []}
            groups[key] = g
        txt = (h.get("text") or "").strip()
        if txt:
            g["texts"].append(txt)
        s = h.get("score")
        if s is not None and (g["score"] is None or s > g["score"]):
            g["score"] = s

    # 근거 문장이 있는 페이지는 texts를 그 문장들로 교체 (문장 단위 하이라이트)
    for key, g in groups.items():
        quotes = [q for q in ev_by_key.get(key, []) if q.strip()]
        if quotes:
            g["texts"] = quotes

    # 근거는 '실제 인용한 페이지(evidence)'만 노출한다 — 채우기 성공/실패, DocQA 모두 동일 규칙.
    # 인용 문장이 없으면(못 찾음/추출 실패) 근거를 표시하지 않는다. (검색만 된 청크는 '근거'가 아님)
    return [g for g in groups.values() if (g["doc"], g["location"]) in ev_by_key]

# 그래프는 1회만 컴파일 (checkpointer 싱글톤 주입). 최초 요청 시 빌드.
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph(checkpointer=get_checkpointer())
    return _graph


class ChatService:
    def __init__(self) -> None:
        self.graph = get_graph()

    async def run(self, req: ChatRequest) -> ChatResponse:
        thread_id = req.thread_id or str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        result = await self.graph.ainvoke(
            {
                "messages": [{"role": "user", "content": req.message}],
                "documents": req.documents,
                "template": req.template.model_dump() if req.template else None,
                "artifacts": {},
            },
            config=config,
        )

        # 마지막 assistant 메시지를 응답으로 (responder/writer/chat이 써넣은 것)
        reply = result["messages"][-1].content if result.get("messages") else ""
        return ChatResponse(reply=reply, thread_id=thread_id, intent=result.get("intent"))

    async def astream(self, req: ChatRequest) -> AsyncIterator[dict]:
        """그래프를 스트리밍 실행하며 이벤트(dict)를 순차 방출.

        이벤트 종류:
          {"type": "meta",  "intent", "thread_id"}  — 라우팅 의도 확정 시 1회
          {"type": "token", "text"}                 — 사용자 노출 노드의 토큰 조각
          {"type": "done",  "reply", "intent", "thread_id"}  — 최종 확정 응답
                                (근거/서식 포함. 클라이언트는 이걸로 본문을 교체한다)

        token은 타자 치는 느낌을 주기 위한 것이고, 정답은 항상 done.reply 다.
        (responder처럼 LLM을 안 쓰는 경로는 token 없이 done만 온다.)
        """
        thread_id = req.thread_id or str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}
        inputs = {
            "messages": [{"role": "user", "content": req.message}],
            "documents": req.documents,
            "template": req.template.model_dump() if req.template else None,
            "artifacts": {},
        }

        intent: str | None = None
        async for mode, chunk in self.graph.astream(
            inputs, config=config, stream_mode=["updates", "messages"]
        ):
            if mode == "updates":
                # supervisor가 intent를 써넣는 순간 한 번 meta로 알린다
                for update in chunk.values():
                    if update and update.get("intent") and intent is None:
                        intent = update["intent"]
                        yield {"type": "meta", "intent": intent, "thread_id": thread_id}
            elif mode == "messages":
                msg, meta = chunk
                if meta.get("langgraph_node") in _STREAMING_NODES:
                    text = getattr(msg, "content", "")
                    if text:
                        yield {"type": "token", "text": text}

        # 최종 상태에서 권위 있는 전체 응답을 가져와 확정 (근거 등 후처리 포함)
        snapshot = await self.graph.aget_state(config)
        values = snapshot.values if snapshot else {}
        messages = values.get("messages", [])
        reply = messages[-1].content if messages else ""
        # DocQA가 검색한 근거 청크 + writer가 뽑은 근거 문장 → 프론트 하이라이트용 구조화 데이터
        artifacts = values.get("artifacts", {})
        sources = _collect_sources(artifacts.get("retrieved", []), artifacts.get("evidence", []))
        # TemplateFill: 채운 항목들 → 프론트 카드용 구조화 데이터.
        # ★ 이번 턴 intent가 TemplateFill일 때만 담는다. (filled_slots는 상태에 남아있어서,
        #    다음 일반채팅/DocQA 턴에서 그대로 실으면 직전 채우기 결과가 또 렌더되는 버그가 남)
        filled = []
        if intent == "TemplateFill":
            filled_slots = sorted(values.get("filled_slots") or [], key=lambda s: s.get("idx", 0))
            filled = [
                {
                    "idx": s.get("idx", 0),
                    "name": s.get("name"),
                    "content": s.get("content"),
                    "skipped": bool(s.get("skipped")),
                    # 근거 문장(evidence)이 있으면 문장 단위 + 실제 쓰인 페이지만 하이라이트
                    "sources": _collect_sources(s.get("sources") or [], s.get("evidence") or []),
                }
                for s in filled_slots
            ]
        yield {
            "type": "done", "reply": reply, "intent": intent, "thread_id": thread_id,
            "sources": sources, "filled": filled,
        }
