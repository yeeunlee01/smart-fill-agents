"""메인 화면: GPT 같은 단일 채팅.

흐름:
  1) 먼저 채팅창 위 '📎 첨부 문서'에서 문서를 올린다. (없으면 에이전트가 첨부 요청)
  2) 문서를 받은 뒤에는 같은 세션에서 자유롭게:
       - 템플릿을 골라 "채워줘" → 채우기 결과 + 근거가 대화로 표시
       - 문서에 대해 질문 → RAG 답변 + 근거
  첨부 문서는 채팅 도중에도 추가/삭제 가능 (expander로 접었다 펴기).
입력 의도(fill/qa)는 supervisor(현재 mock)가 분기한다.
"""
import streamlit as st

from components.slot_card import render_slot_card
from store import (
    answer_question,
    classify_intent,
    fill_template,
    get_template,
    list_templates,
)

if "chat" not in st.session_state:
    st.session_state.chat = []


# ---------------------------------------------------------------------------
# 사이드바: 템플릿 선택 + 대화 비우기
# ---------------------------------------------------------------------------
with st.sidebar:
    st.subheader("📄 템플릿")
    names = [t["name"] for t in list_templates()]
    active = st.selectbox("채울 템플릿", names) if names else None
    if not names:
        st.info("'템플릿 관리'에서 먼저 만들어주세요.")

    st.divider()
    if st.button("🧹 대화 비우기", use_container_width=True):
        st.session_state.chat = []
        st.rerun()


# ---------------------------------------------------------------------------
# 메시지 렌더링
# ---------------------------------------------------------------------------
def render_assistant(msg: dict, idx: int) -> None:
    kind = msg.get("kind")
    if kind == "fill":
        result = msg["result"]
        st.markdown(
            f"✅ **{result['template_name']}** 템플릿을 채웠어요 "
            f"(slot {len(result['slots'])}개)"
        )
        st.caption("사용한 문서: " + (", ".join(result["files"]) or "없음"))
        for slot in result["slots"]:
            render_slot_card(slot)
        final = "\n\n".join(f"## {s['name']}\n{s['content']}" for s in result["slots"])
        st.download_button(
            "⬇️ 최종 결과 다운로드 (.md)",
            data=final,
            file_name=f"{result['template_name']}_filled.md",
            mime="text/markdown",
            key=f"dl_{idx}",
        )
    elif kind == "qa":
        st.write(msg["answer"])
        with st.expander(f"📎 근거 ({len(msg['sources'])}개)"):
            for src in msg["sources"]:
                st.markdown(
                    f"- **{src['doc']}** · {src['location']} · 유사도 `{src['score']}`"
                )
                st.caption(src["snippet"])
    else:  # 일반 텍스트 (안내 등)
        st.write(msg["text"])


# ---------------------------------------------------------------------------
# 화면
# ---------------------------------------------------------------------------
st.title("💬 smart-fill-agents")

# --- 채팅창 위 고정: 첨부 문서 영역 (접었다 펴기) ---
prev = st.session_state.get("docs") or []
with st.expander(
    f"📎 첨부 문서 ({len(prev)}개) — 추가/삭제 가능",
    expanded=(len(prev) == 0),  # 비어있으면 펼쳐서 눈에 띄게
):
    files = st.file_uploader(
        "문서를 올리거나, 파일 옆 ✕로 삭제하세요",
        type=["pptx", "html", "pdf", "txt", "docx"],
        accept_multiple_files=True,
        key="docs",
    )
file_names = [f.name for f in files] if files else []

# 접어도 항상 보이는 첨부 목록
if file_names:
    st.caption("📎 첨부됨: " + " · ".join(f"`{n}`" for n in file_names))

st.divider()

# 에이전트 인사 (항상 첫 말풍선). 문서 첨부 여부에 따라 안내가 달라짐.
with st.chat_message("assistant"):
    if not file_names:
        st.write(
            "안녕하세요! 문서를 채워드리거나 문서에 대해 답해드릴게요.\n\n"
            "**먼저 위쪽 '📎 첨부 문서'에 문서를 올려주세요.**"
        )
    else:
        st.write(
            f"문서 **{len(file_names)}개**를 받았어요. 이제 자유롭게 요청하세요:\n\n"
            "- 왼쪽에서 템플릿을 고른 뒤 **\"채워줘\"** 라고 말하면 템플릿을 채워드려요\n"
            "- 문서에 대해 **궁금한 점을 질문**하면 근거와 함께 답해드려요"
        )

# 대화 히스토리
for i, msg in enumerate(st.session_state.chat):
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.write(msg["text"])
        else:
            render_assistant(msg, i)


# ---------------------------------------------------------------------------
# 입력 처리
# ---------------------------------------------------------------------------
prompt = st.chat_input("템플릿을 채우거나, 문서에 대해 질문하세요")

if prompt:
    st.session_state.chat.append({"role": "user", "text": prompt})

    # 문서 첨부가 먼저다 — 없으면 진행 불가
    if not file_names:
        st.session_state.chat.append(
            {
                "role": "assistant",
                "kind": "text",
                "text": "먼저 위쪽 '📎 첨부 문서'에 문서를 올려주세요. 문서를 받아야 채우거나 답변할 수 있어요.",
            }
        )
    else:
        intent = classify_intent(prompt)
        if intent == "fill":
            if not active:
                st.session_state.chat.append(
                    {
                        "role": "assistant",
                        "kind": "text",
                        "text": "채울 템플릿을 왼쪽에서 먼저 선택해주세요 📄",
                    }
                )
            else:
                result = fill_template(get_template(active), file_names)
                st.session_state.chat.append(
                    {"role": "assistant", "kind": "fill", "result": result}
                )
        else:  # qa
            ans = answer_question(prompt, file_names)
            st.session_state.chat.append(
                {
                    "role": "assistant",
                    "kind": "qa",
                    "answer": ans["answer"],
                    "sources": ans["sources"],
                }
            )
    st.rerun()
