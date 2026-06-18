"""Streamlit 진입점 = 네비게이션 라우터.

화면은 둘뿐: 💬 채팅(메인) / ⚙️ 템플릿 관리.
채우기와 질의응답은 모두 채팅 안에서 처리된다 (supervisor 라우터가 의도 분기).
"""
import streamlit as st

from store import init_store

st.set_page_config(page_title="smart-fill-agents", page_icon="📝", layout="wide")
init_store()

chat_page = st.Page("views/chat.py", title="채팅", icon="💬", default=True)
templates_page = st.Page("views/templates.py", title="템플릿 관리", icon="⚙️")

st.navigation([chat_page, templates_page]).run()
