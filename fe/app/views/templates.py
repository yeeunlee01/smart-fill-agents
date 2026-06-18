"""템플릿 관리.

기본 화면 = 등록된 템플릿 '라이브러리'(카드 갤러리).
➕ 새 템플릿 → LLM이 slot 분할 → 각 slot 확인/편집 → 저장.
카드의 ✏️ 편집으로 기존 템플릿 slot도 다시 손볼 수 있다.
"""
import streamlit as st

from store import (
    delete_template,
    get_template,
    list_templates,
    save_template,
    split_into_slots,
)

st.title("⚙️ 템플릿 관리")

mode = st.session_state.setdefault("tpl_mode", "library")


# ---------------------------------------------------------------------------
# 모드 전환 헬퍼
# ---------------------------------------------------------------------------
def go_library() -> None:
    st.session_state.tpl_mode = "library"
    st.session_state.pop("draft_slots", None)
    st.session_state.pop("draft_raw", None)
    st.session_state.pop("tpl_editing", None)


def go_editor(name: str | None) -> None:
    """name=None 이면 새 템플릿, 아니면 기존 편집."""
    st.session_state.tpl_mode = "editor"
    st.session_state.tpl_editing = name
    if name:
        t = get_template(name)
        st.session_state.draft_slots = [dict(s) for s in t["slots"]]
        st.session_state.draft_raw = t["raw_text"]
    else:
        st.session_state.pop("draft_slots", None)
        st.session_state.draft_raw = ""


# ===========================================================================
# 라이브러리 (기본)
# ===========================================================================
if mode == "library":
    st.caption("등록된 템플릿을 카드로 관리하세요. 첫 카드의 ➕로 추가할 수 있어요.")

    templates = list_templates()
    COLS = 4  # 한 줄당 카드 수 (많을수록 카드 폭이 좁아짐)
    CARD_HEIGHT = 320  # 세로로 긴 카드 형태
    SLOT_SCROLL_H = 120  # 카드 안 slot 스크롤 영역 높이 (버튼 공간 확보)
    cols = st.columns(COLS)

    # 첫 번째 카드 = 새 템플릿 추가
    with cols[0]:
        with st.container(border=True, height=CARD_HEIGHT):
            st.markdown("### ➕ 새 템플릿")
            st.caption("새 템플릿을 추가합니다")
            st.container(height=45, border=False)  # 세로 가운데로 밀기 (스페이서)
            _, mid, _ = st.columns([1, 2, 1])  # 가로 가운데 + 절반 폭
            if mid.button("만들기", key="add_new", type="primary", use_container_width=True):
                go_editor(None)
                st.rerun()

    # 이어서 등록된 템플릿 카드들 (추가 카드 다음 칸부터)
    for i, t in enumerate(templates):
        with cols[(i + 1) % COLS]:
            with st.container(border=True, height=CARD_HEIGHT):
                st.markdown(f"### 📄 {t['name']}")
                st.caption(f"slot {len(t['slots'])}개")

                # slot 내용 (스크롤 영역)
                with st.container(height=SLOT_SCROLL_H, border=True):
                    if not t["slots"]:
                        st.write("_(slot 없음)_")
                    else:
                        st.markdown(
                            "\n".join(
                                f"- **{s['name']}** — {s['definition']}"
                                for s in t["slots"]
                            )
                        )

                # 하단 버튼 (좌: 편집 / 우: 삭제)
                c1, c2 = st.columns(2)
                if c1.button("✏️ 편집", key=f"edit_{i}", use_container_width=True):
                    go_editor(t["name"])
                    st.rerun()
                if c2.button("🗑️ 삭제", key=f"del_{i}", use_container_width=True):
                    delete_template(t["name"])
                    st.rerun()


# ===========================================================================
# 에디터 (추가 / 편집)
# ===========================================================================
else:
    is_new = st.session_state.get("tpl_editing") is None

    if st.button("← 목록으로"):
        go_library()
        st.rerun()

    st.subheader("➕ 새 템플릿" if is_new else f"✏️ 편집: {st.session_state.tpl_editing}")

    # 이름 (편집 시에는 고정)
    name = st.text_input(
        "템플릿 이름",
        value="" if is_new else st.session_state.tpl_editing,
        placeholder="예: 사업계획서",
        disabled=not is_new,
    )

    # --- 1단계: 원문 입력 → slot 분할 (새 템플릿이고 아직 분할 전일 때만) ---
    if is_new and not st.session_state.get("draft_slots"):
        tab_paste, tab_upload = st.tabs(["✍️ 텍스트 붙여넣기", "📎 파일 업로드"])
        raw_text = ""
        with tab_paste:
            raw_text = st.text_area(
                "템플릿 원문 (항목을 줄바꿈으로 구분)",
                height=200,
                placeholder="사업 개요\n시장 분석\n수익 모델\n팀 구성",
            )
        with tab_upload:
            up = st.file_uploader("템플릿 파일 (PPT/HTML 등)", type=["pptx", "html", "txt"])
            if up is not None:
                # TODO: be에서 파일 파싱 → 원문 텍스트 추출
                st.info(f"업로드됨: {up.name} — (파싱은 추후 be에서 처리)")
                raw_text = raw_text or up.name

        if st.button("🤖 LLM으로 slot 분할", type="primary", disabled=not raw_text):
            with st.spinner("slot으로 나누는 중..."):
                st.session_state.draft_slots = split_into_slots(raw_text)
                st.session_state.draft_raw = raw_text
            st.rerun()

    # --- 2단계: slot 확인/편집 → 저장 ---
    if st.session_state.get("draft_slots"):
        st.divider()
        st.subheader("slot 확인 / 편집")
        st.caption("행 추가·삭제 가능. 각 slot 이름과 정의를 직접 수정하세요.")

        edited = st.data_editor(
            st.session_state.draft_slots,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "name": st.column_config.TextColumn("slot 이름", required=True),
                "definition": st.column_config.TextColumn("정의 (무엇을 채울지)", width="large"),
            },
            key="slot_editor",
        )

        if st.button("💾 저장", type="primary", disabled=not name):
            slots = [s for s in edited if s.get("name")]
            save_template(name, st.session_state.get("draft_raw", ""), slots)
            go_library()
            st.rerun()
