import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
from data.db import init_db
from ui.import_page import render_import_page
from ui.input_page import render_input_page
from ui.result_page import render_result_page
from ui.order_page import render_order_page
from ui.history_page import render_history_page
from ui.settings_page import render_settings_page

st.set_page_config(
    page_title="운영재고 자동 산출 시스템",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()

pages = {
    "📂 백데이터 가져오기": render_import_page,
    "📥 월별 실적 입력": render_input_page,
    "📊 운영재고 산출 결과": render_result_page,
    "🚚 현재고 입력·발주 산출": render_order_page,
    "📈 이력 조회 및 추세": render_history_page,
    "⚙️ 파라미터 설정": render_settings_page,
}

st.sidebar.title("📦 운영재고 시스템")
st.sidebar.markdown("---")
page = st.sidebar.selectbox("메뉴", list(pages.keys()))
st.sidebar.markdown("---")
st.sidebar.caption("Paper SCM Team | v1.0")

pages[page]()
