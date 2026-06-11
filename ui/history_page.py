import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from data.db import get_stock_results, get_products
from utils.exporter import export_results_to_excel


def render_history_page():
    st.title("📈 이력 조회 및 추세")

    products = get_products()
    product_ids = [p["product_id"] for p in products]

    # ── Filters ────────────────────────────────────────────────────────────────
    with st.sidebar:
        st.subheader("필터")
        selected_products = st.multiselect(
            "제품 선택",
            product_ids,
            default=product_ids,
            key="history_products",
        )

        default_end = datetime.now()
        default_start = default_end - timedelta(days=365)
        date_from = st.date_input("시작월", value=default_start, key="hist_from")
        date_to = st.date_input("종료월", value=default_end, key="hist_to")

        from_yyyymm = date_from.strftime("%Y%m")
        to_yyyymm = date_to.strftime("%Y%m")

        limit = st.number_input("최대 조회 건수", min_value=10, max_value=1000, value=200, step=10)

    # ── Load Data ──────────────────────────────────────────────────────────────
    all_results = get_stock_results(limit=int(limit))
    if not all_results:
        st.warning("이력 데이터가 없습니다. 운영재고 산출을 먼저 실행해 주세요.")
        return

    df = pd.DataFrame(all_results)

    # Filter by product and date
    if selected_products:
        df = df[df["product_id"].isin(selected_products)]
    df = df[
        (df["calc_yyyymm"] >= from_yyyymm) & (df["calc_yyyymm"] <= to_yyyymm)
    ]

    if df.empty:
        st.info("선택한 기간/제품에 해당하는 데이터가 없습니다.")
        return

    # ── Summary Metrics ────────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("조회 레코드 수", f"{len(df):,} 건")
    m2.metric("제품 수", f"{df['product_id'].nunique()} 개")
    m3.metric("평균 운영재고", f"{df['operating_stock'].mean():,.1f} 톤")
    m4.metric("평균 운영재고일수", f"{df['operating_days'].mean():.1f} 일")

    st.divider()

    # ── Historical Table ───────────────────────────────────────────────────────
    st.subheader("📋 이력 조회 결과")

    display_cols = [
        "product_id", "calc_yyyymm", "target_yyyymm", "service_level",
        "z_value", "sigma_d", "sigma_lt", "avg_lt", "d_prime",
        "safety_stock_independent", "safety_stock_dependent",
        "cycle_stock", "operating_stock", "operating_days",
    ]
    existing_cols = [c for c in display_cols if c in df.columns]
    display_df = df[existing_cols].copy()

    col_rename = {
        "product_id": "제품", "calc_yyyymm": "산출월", "target_yyyymm": "대상월",
        "service_level": "서비스수준", "z_value": "Z값", "sigma_d": "σd",
        "sigma_lt": "σLT", "avg_lt": "평균LT", "d_prime": "d'",
        "safety_stock_independent": "안전재고(독립)", "safety_stock_dependent": "안전재고(종속)",
        "cycle_stock": "사이클재고", "operating_stock": "운영재고(톤)", "operating_days": "운영재고일",
    }
    display_df.rename(columns=col_rename, inplace=True)

    st.dataframe(display_df, use_container_width=True, height=400)

    # ── Trend Chart ────────────────────────────────────────────────────────────
    st.subheader("📊 제품별 운영재고 추세")

    chart_metric = st.selectbox(
        "지표 선택",
        ["운영재고(톤)", "운영재고일수", "안전재고(독립)", "사이클재고"],
        key="trend_metric",
    )
    metric_col_map = {
        "운영재고(톤)": "operating_stock",
        "운영재고일수": "operating_days",
        "안전재고(독립)": "safety_stock_independent",
        "사이클재고": "cycle_stock",
    }
    metric_col = metric_col_map[chart_metric]

    if metric_col in df.columns:
        fig = go.Figure()
        for pid in selected_products:
            prod_df = df[df["product_id"] == pid].sort_values("calc_yyyymm")
            if not prod_df.empty:
                fig.add_scatter(
                    x=prod_df["calc_yyyymm"].tolist(),
                    y=prod_df[metric_col].tolist(),
                    mode="lines+markers",
                    name=pid,
                )
        fig.update_layout(
            title=f"제품별 {chart_metric} 추세",
            xaxis_title="산출월",
            yaxis_title=chart_metric,
            height=450,
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Export ─────────────────────────────────────────────────────────────────
    st.subheader("📥 엑셀 내보내기")
    col1, col2 = st.columns([2, 1])
    with col1:
        export_filename = st.text_input(
            "파일명",
            value=f"운영재고_이력_{datetime.now().strftime('%Y%m%d')}.xlsx",
        )
    with col2:
        st.write("")
        st.write("")
        if st.button("📥 엑셀 다운로드", use_container_width=True):
            try:
                excel_bytes = export_results_to_excel(df, export_filename)
                st.download_button(
                    label="💾 다운로드",
                    data=excel_bytes,
                    file_name=export_filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            except Exception as e:
                st.error(f"엑셀 생성 오류: {e}")
