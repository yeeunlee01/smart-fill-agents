"""라우팅 테이블: supervisor의 판단(next) -> 실제 노드 이름.

supervisor가 state["next"]에 아래 키 중 하나를 써넣으면,
graph.py의 conditional_edges가 이 매핑을 보고 해당 노드로 분기한다.

흐름 개요:
    START → supervisor ─┬─ Chat         → chat                       → END
                        ├─ DocQA        → researcher → writer        → END
                        ├─ TemplateFill → fill_dispatch ─(Send)→ ...  → END
                        └─ Ask          → responder                  → END
"""

# 노드 이름 상수 (graph.py의 add_node 이름과 일치시킬 것)
SUPERVISOR = "supervisor"
CHAT = "chat"                 # Chat: 문서 없이 잡담/안내 응답
RESPONDER = "responder"       # Ask: 안내 메시지만 내고 종료 (문서/템플릿 미비)
RESEARCHER = "researcher"     # DocQA: RAG 검색
WRITER = "writer"             # DocQA: 답변 작성
REVIEWER = "reviewer"         # TemplateFill: 산출물 검수 (fill 단계에서 배선)
FILL_DISPATCH = "fill_dispatch"    # TemplateFill: slot별 Send fan-out 진입점
SLOT_FILLER = "slot_filler"        # TemplateFill: slot 1개 채우기 (병렬)
FILL_AGGREGATOR = "fill_aggregator"  # TemplateFill: 채운 slot들을 모아 결과 문서화

# supervisor의 의도(next) -> 분기 대상
ROUTE_MAP = {
    "Chat": CHAT,
    "DocQA": RESEARCHER,
    "TemplateFill": FILL_DISPATCH,
    "Ask": RESPONDER,
}
