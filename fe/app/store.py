"""페이지 간 공유 상태 + mock 로직.

⚠️ 지금은 화면(UI) 확인용 mock이다.
   실제 로직(LLM slot 분할 / Milvus 적재 / RAG 채우기)은 나중에 be(FastAPI)
   호출로 교체한다. 교체 지점마다 # TODO 로 표시해둠.
"""
import time

import streamlit as st


# ---------------------------------------------------------------------------
# 상태 초기화
# ---------------------------------------------------------------------------
def init_store() -> None:
    """session_state 초기화. 모든 페이지 상단에서 호출."""
    if "templates" not in st.session_state:
        st.session_state.templates = [_sample_template()]
    if "fill_results" not in st.session_state:
        # template_name -> 채우기 결과
        st.session_state.fill_results = {}


def _sample_template() -> dict:
    """데모용 샘플 템플릿 1개."""
    return {
        "name": "사업계획서 (샘플)",
        "raw_text": "사업 개요\n시장 분석\n수익 모델\n팀 구성",
        "slots": [
            {"name": "사업 개요", "definition": "사업의 목적과 배경을 2~3문장으로 요약"},
            {"name": "시장 분석", "definition": "타깃 시장 규모와 경쟁 현황"},
            {"name": "수익 모델", "definition": "주요 매출원과 과금 방식"},
            {"name": "팀 구성", "definition": "핵심 멤버와 역할"},
        ],
    }


# ---------------------------------------------------------------------------
# 템플릿 CRUD (session_state 기반)
# ---------------------------------------------------------------------------
def list_templates() -> list[dict]:
    return st.session_state.templates


def get_template(name: str) -> dict | None:
    return next((t for t in st.session_state.templates if t["name"] == name), None)


def save_template(name: str, raw_text: str, slots: list[dict]) -> None:
    existing = get_template(name)
    if existing:
        existing.update(raw_text=raw_text, slots=slots)
    else:
        st.session_state.templates.append(
            {"name": name, "raw_text": raw_text, "slots": slots}
        )


def delete_template(name: str) -> None:
    st.session_state.templates = [
        t for t in st.session_state.templates if t["name"] != name
    ]


# ---------------------------------------------------------------------------
# mock 로직 (→ 나중에 be 호출로 교체)
# ---------------------------------------------------------------------------
def split_into_slots(raw_text: str) -> list[dict]:
    """템플릿 원문을 slot 단위로 분할.

    # TODO: be의 LLM 호출로 교체 (POST /api/v1/templates/split 등)
    지금은 단순히 줄 단위로 나눠서 slot 후보를 만든다.
    """
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    return [
        {"name": ln, "definition": "이 항목에 채울 내용 정의 (LLM 생성, 수정 가능)"}
        for ln in lines
    ]


def fill_template(template: dict, file_names: list[str]) -> dict:
    """첨부 파일을 Milvus에 넣고, 각 slot을 RAG로 채운다 (병렬).

    # TODO: 실제로는 be 호출
    #   1) 파일 업로드 + Milvus 적재 (ingest)
    #   2) 각 slot 병렬 RAG 검색 → LLM 작성
    지금은 가짜 결과/근거를 생성한다.
    """
    time.sleep(0.4)  # 처리되는 느낌만 (mock)
    slots = []
    for s in template["slots"]:
        slots.append(
            {
                "name": s["name"],
                "definition": s["definition"],
                "content": f"[자동 생성] '{s['name']}' 항목에 대한 내용입니다. "
                f"첨부 문서에서 검색된 근거를 바탕으로 작성된 자리(mock)입니다.",
                "status": "done",
                "sources": _mock_sources(file_names),
            }
        )
    return {"template_name": template["name"], "files": file_names, "slots": slots}


def classify_intent(text: str) -> str:
    """사용자 입력이 '채우기(fill)'인지 '질문(qa)'인지 판단.

    # TODO: be의 supervisor 라우터로 교체 (LLM 의도 분류).
    지금은 키워드 기반 mock.
    """
    fill_keywords = ["채워", "채우", "작성", "만들어", "완성", "fill"]
    if any(k in text for k in fill_keywords):
        return "fill"
    return "qa"


def answer_question(question: str, file_names: list[str]) -> dict:
    """첨부 문서 기반 질의응답 (RAG).

    # TODO: be 호출 — Milvus 검색 → LLM 답변.
    지금은 가짜 답변/근거.
    """
    time.sleep(0.3)
    return {
        "answer": f"[자동응답] '{question}'에 대한 답변입니다. "
        f"첨부 문서에서 검색된 내용을 바탕으로 작성된 자리(mock)입니다.",
        "sources": _mock_sources(file_names),
    }


def _mock_sources(file_names: list[str]) -> list[dict]:
    """slot을 채우는 데 쓴 근거 문서/위치 (mock)."""
    docs = file_names or ["sample_doc.pptx"]
    out = []
    for i, doc in enumerate(docs[:2]):
        out.append(
            {
                "doc": doc,
                "location": f"슬라이드/페이지 {i + 3}",
                "snippet": "…이 부분이 해당 slot의 근거로 검색된 텍스트 일부입니다…",
                "score": round(0.92 - i * 0.07, 2),
            }
        )
    return out
