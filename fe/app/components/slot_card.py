"""채워진 slot 1개를 카드 형태로 렌더링 (내용 + 근거). 페이지 2/3에서 재사용."""
import streamlit as st


def render_slot_card(slot: dict) -> None:
    with st.container(border=True):
        st.markdown(f"#### {slot['name']}")
        st.caption(f"정의: {slot.get('definition', '-')}")
        st.write(slot.get("content", "_(아직 채워지지 않음)_"))

        sources = slot.get("sources", [])
        with st.expander(f"📎 근거 보기 ({len(sources)}개 출처)"):
            if not sources:
                st.write("근거 없음")
            for src in sources:
                st.markdown(
                    f"- **{src['doc']}** · {src['location']} "
                    f"· 유사도 `{src['score']}`"
                )
                st.caption(src["snippet"])
