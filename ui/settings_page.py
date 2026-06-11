import streamlit as st
from datetime import datetime
from data.db import get_setting, set_setting, get_products, get_conn


def render_settings_page():
    st.title("⚙️ 파라미터 설정")

    # ── ECOS API Key ─────────────────────────────────────────────────────────
    st.header("🔑 ECOS API 키 설정")
    current_key = get_setting("ecos_api_key", "")

    if not current_key:
        st.warning("ECOS API 키가 설정되지 않았습니다. ML 기능은 캐시된 데이터만 사용합니다.")

    new_key = st.text_input(
        "ECOS API 키",
        value=current_key,
        type="password",
        placeholder="한국은행 ECOS Open API 키를 입력하세요",
        help="https://ecos.bok.or.kr/에서 발급 가능합니다.",
    )

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("💾 API 키 저장", use_container_width=True):
            set_setting("ecos_api_key", new_key.strip())
            st.success("API 키가 저장되었습니다.")
            st.rerun()

    with col2:
        if st.button("🔗 API 연결 테스트", use_container_width=True):
            with st.spinner("ECOS API 연결 중..."):
                try:
                    from ml.ecos_client import EcosApiClient
                    client = EcosApiClient()
                    year = datetime.now().year
                    result = client.fetch_gdp_growth(year)
                    if result.get("source") == "ECOS_API":
                        st.success(f"✅ 연결 성공! {year}년 연간 GDP 성장률: {result['annual']:.2f}%")
                    else:
                        st.warning(f"⚠️ API 키 오류 또는 응답 없음. 캐시 데이터 사용 중 (annual={result['annual']:.2f}%)")
                except Exception as e:
                    st.error(f"❌ 연결 실패: {e}")

    st.divider()

    # ── Service Level Settings ────────────────────────────────────────────────
    st.header("📊 제품별 기본 서비스 수준")
    products = get_products()

    with st.form("service_level_form"):
        updated_levels = {}
        cols = st.columns(5)
        for i, p in enumerate(products):
            with cols[i % 5]:
                sl = st.selectbox(
                    p["product_id"],
                    options=[0.90, 0.95, 0.99],
                    index=[0.90, 0.95, 0.99].index(p.get("service_level", 0.95)),
                    format_func=lambda x: f"{int(x*100)}%",
                    key=f"sl_{p['product_id']}",
                )
                updated_levels[p["product_id"]] = sl

        if st.form_submit_button("저장", use_container_width=True):
            with get_conn() as conn:
                for pid, sl in updated_levels.items():
                    conn.execute(
                        "UPDATE product SET service_level=? WHERE product_id=?",
                        (sl, pid),
                    )
            st.success("서비스 수준이 업데이트되었습니다.")
            st.rerun()

    st.divider()

    # ── Working Days Setting ──────────────────────────────────────────────────
    st.header("📅 월 영업일수 설정")
    current_working_days = int(get_setting("working_days", "22"))
    new_working_days = st.number_input(
        "월 영업일수",
        min_value=15,
        max_value=31,
        value=current_working_days,
        step=1,
        help="d' = 월계획량 / 영업일수 계산에 사용됩니다.",
    )
    if st.button("영업일수 저장"):
        set_setting("working_days", str(int(new_working_days)))
        st.success(f"영업일수가 {int(new_working_days)}일로 저장되었습니다.")

    st.divider()

    # ── Dummy Data Generation ─────────────────────────────────────────────────
    st.header("🗄️ 더미 데이터 생성")
    st.info("2023-01 ~ 2025-12 기간의 샘플 데이터를 생성합니다. 기존 판매/리드타임 데이터가 삭제됩니다.")

    if st.button("🔄 더미 데이터 재생성", type="primary"):
        progress = st.progress(0, text="더미 데이터 생성 중...")
        status_area = st.empty()
        try:
            from data.dummy_generator import PRODUCTS as DUMMY_PRODUCTS, generate_dummy_data
            # Patch to show progress
            total = len(DUMMY_PRODUCTS)
            for i, (pid, *_) in enumerate(DUMMY_PRODUCTS):
                progress.progress((i + 1) / total, text=f"[{pid}] 데이터 생성 중... ({i+1}/{total})")
                status_area.info(f"처리 중: {pid}")
            generate_dummy_data()
            progress.progress(1.0, text="완료!")
            st.success("더미 데이터가 성공적으로 생성되었습니다.")
        except Exception as e:
            st.error(f"더미 데이터 생성 실패: {e}")

    st.divider()

    # ── Trend Update ──────────────────────────────────────────────────────────
    st.header("📈 제품 추세 재분류")
    if st.button("추세 재분류 실행"):
        with st.spinner("추세 분석 중..."):
            try:
                from ml.trend_classifier import TrendClassifier
                classifier = TrendClassifier()
                results = classifier.update_all_products()
                trend_labels = {"growth": "📈 성장", "decline": "📉 감소", "stable": "➡️ 안정"}
                result_rows = [{"제품": k, "추세": trend_labels.get(v, v)} for k, v in results.items()]
                import pandas as pd
                st.dataframe(pd.DataFrame(result_rows), use_container_width=True)
                st.success("추세 분류가 완료되었습니다.")
            except Exception as e:
                st.error(f"추세 분류 실패: {e}")
