import math
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from data.db import get_stock_results, get_monthly_sales, get_leadtime_records, get_products
from core.safety_stock import SafetyStockEngine, Z_TABLE
from core.operating_stock import OperatingStockEngine


# ── 캐시: DB 조회 결과를 세션 내에 재사용 ─────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _cached_products():
    rows = get_products()
    return {p["product_id"]: p for p in rows}

@st.cache_data(ttl=300, show_spinner=False)
def _cached_sales(pid, window):
    return get_monthly_sales(pid, window_months=window)

@st.cache_data(ttl=300, show_spinner=False)
def _cached_lt(pid, window):
    return get_leadtime_records(pid, window_months=window)

@st.cache_data(ttl=300, show_spinner=False)
def _cached_gdp(year):
    from ml.ecos_client import EcosApiClient
    return EcosApiClient().fetch_gdp_growth(year)

@st.cache_data(ttl=300, show_spinner=False)
def _fit_forecaster(pid):
    """지종 1개 학습 결과를 캐시 — DB 재조회 없음"""
    from ml.demand_forecast import DemandForecaster
    f = DemandForecaster()
    f.fit(pid)
    return f.models.get(pid, {})


def _build_forecast(results, forecast_pids, forecast_sl, wdays_fc, name_map=None):
    if name_map is None:
        name_map = {}
    """연간 예측 계산 — 순수 계산만, UI 없음"""
    ss_eng  = SafetyStockEngine()
    op_eng  = OperatingStockEngine()
    z_fc    = Z_TABLE[forecast_sl]
    pc_map  = {pid: p["pc_days"] for pid, p in _cached_products().items()}
    stats   = {r["product_id"]: r for r in results if r["product_id"] in forecast_pids}

    now           = datetime.now()
    current_year  = now.year
    current_month = now.month
    future_months = [f"{current_year}{m:02d}" for m in range(current_month, 13)]

    # GDP 분기별 사전 수집 (1회)
    gdp_raw = _cached_gdp(current_year)
    gdp_by_q = {
        "Q1": gdp_raw.get("Q1", 2.5),
        "Q2": gdp_raw.get("Q2", 2.5),
        "Q3": gdp_raw.get("Q3", 2.5),
        "Q4": gdp_raw.get("Q4", 2.5),
    }

    def get_q(month):
        return f"Q{(month - 1) // 3 + 1}"

    # 지종별 모델 사전 학습 (캐시)
    models = {pid: _fit_forecaster(pid) for pid in forecast_pids}

    rows       = []
    chart_data = {}

    for yyyymm in future_months:
        mo  = int(yyyymm[4:])
        gdp = gdp_by_q.get(get_q(mo), 2.5)
        month_label = f"{current_year}.{mo:02d}"

        for pid in forecast_pids:
            stat     = stats.get(pid, {})
            sigma_d  = stat.get("sigma_d", 0)
            sigma_lt = stat.get("sigma_lt", 1.0)
            avg_lt   = stat.get("avg_lt", 5.0)
            pc       = pc_map.get(pid, 4)

            model    = models.get(pid, {})
            actuals  = model.get("actuals", [3000.0])
            base_n   = model.get("n", len(actuals))
            slope, intercept = model.get("lr", (0.0, actuals[-1] if actuals else 3000.0))
            month_offset = mo - current_month
            future_idx   = base_n + month_offset

            lr_pred  = max(slope * (future_idx + gdp * 10) + intercept, 100.0)
            last_ema = model.get("last_ema", actuals[-1] if actuals else 3000.0)
            ema_pred = max(last_ema + slope * month_offset, 100.0)

            # MAPE (미리 저장된 gdp_values 사용, 없으면 2.5 대체)
            gdp_vals = model.get("gdp_values") or [2.5] * base_n
            safe_n   = min(base_n, len(gdp_vals), len(actuals))
            if safe_n >= 2:
                lr_hist = [slope * (i + gdp_vals[i] * 10) + intercept for i in range(safe_n)]
                mape    = sum(abs((a - p) / a) for a, p in zip(actuals[:safe_n], lr_hist) if a != 0) / safe_n * 100
            else:
                mape = 99.0

            est_qty    = lr_pred if mape < 10.0 else ema_pred
            model_used = "선형회귀(GDP반영)" if mape < 10.0 else "EMA"

            d_prime = est_qty / wdays_fc
            ss  = ss_eng.calc_safety_stock(z_fc, pc, avg_lt, sigma_d, d_prime, sigma_lt)
            cy  = op_eng.calc_cycle_stock(d_prime, pc, avg_lt)
            op  = op_eng.calc_operating_stock(ss["independent"], cy, d_prime)

            rows.append({
                "월":            month_label,
                "지종":          name_map.get(pid, pid),
                "추정판매량(톤)": round(est_qty, 0),
                "추정모델":      model_used,
                "안전재고(톤)":  round(ss["independent"], 1),
                "사이클재고(톤)": round(cy, 1),
                "운영재고(톤)":  round(op["operating_stock_ton"], 1),
                "운영재고(일)":  round(op["operating_stock_days"], 1),
                "GDP적용(%)":    round(gdp, 2),
            })
            chart_data.setdefault(pid, []).append((month_label, round(op["operating_stock_ton"], 1)))

    return pd.DataFrame(rows), chart_data


def render_result_page():
    st.title("📊 운영재고 산출 결과")

    results      = st.session_state.get("calc_results", [])
    target_yyyymm = st.session_state.get("calc_target_yyyymm", "")

    if not results:
        db_results = get_stock_results(limit=500)
        if db_results:
            latest_calc = max(r["calc_yyyymm"] for r in db_results)
            all_latest  = [r for r in db_results if r["calc_yyyymm"] == latest_calc]
            # 산출된 전체 월 목록 — 현재월 이후만 표시
            current_yyyymm = datetime.now().strftime("%Y%m")
            all_months  = sorted(set(
                r.get("target_yyyymm", "") for r in all_latest
                if r.get("target_yyyymm") and r.get("target_yyyymm") >= current_yyyymm
            ))

            # 월 선택 UI
            month_labels = {m: f"{m[:4]}년 {m[4:]}월" for m in all_months}
            selected_month = st.selectbox(
                "📅 조회 대상월 선택",
                options=all_months,
                format_func=lambda m: month_labels.get(m, m),
                index=0,
                key="result_month_select"
            )
            st.caption(f"산출월: {latest_calc} | 산출 범위: {len(all_months)}개월 ({all_months[0][:4]}년 {all_months[0][4:]}월 ~ {all_months[-1][:4]}년 {all_months[-1][4:]}월)")

            # 선택월 결과 — 제품당 최신 1건만 (중복 레코드 방어)
            month_rows = [r for r in all_latest if r.get("target_yyyymm") == selected_month]
            seen = {}
            for r in month_rows:
                pid = r.get("product_id")
                if pid not in seen:
                    seen[pid] = r
            results       = list(seen.values())
            target_yyyymm = selected_month
        else:
            st.warning("산출된 운영재고 결과가 없습니다. '월별 실적 입력' 페이지에서 산출을 실행해 주세요.")
            return

    if target_yyyymm:
        st.subheader(f"대상월: {target_yyyymm[:4]}년 {target_yyyymm[4:]}월")

    df         = pd.DataFrame(results)
    ss_engine  = SafetyStockEngine()
    op_engine  = OperatingStockEngine()
    prod_map   = _cached_products()
    pc_map     = {pid: p["pc_days"] for pid, p in prod_map.items()}
    prod_ids   = [p["product_id"] for p in prod_map.values()]
    name_map   = {pid: p["product_name"] for pid, p in prod_map.items()}
    def pname(pid): return name_map.get(pid, pid)

    # ── 요약 지표 ─────────────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("총 운영재고",       f"{df['operating_stock'].sum():,.0f} 톤"        if 'operating_stock'          in df else "—")
    m2.metric("평균 운영재고일수",  f"{df['operating_days'].mean():.1f} 일"         if 'operating_days'           in df else "—")
    m3.metric("총 안전재고(독립)", f"{df['safety_stock_independent'].sum():,.0f} 톤" if 'safety_stock_independent' in df else "—")
    m4.metric("총 사이클재고",     f"{df['cycle_stock'].sum():,.0f} 톤"             if 'cycle_stock'              in df else "—")

    st.divider()

    # ── 서비스수준별 탭 ───────────────────────────────────────────────────────
    tab90, tab95, tab99 = st.tabs(["서비스수준 90%", "서비스수준 95%", "서비스수준 99%"])
    for tab, sl in [(tab90, 0.90), (tab95, 0.95), (tab99, 0.99)]:
        with tab:
            z    = Z_TABLE[sl]
            rows = []
            for r in results:
                pc       = pc_map.get(r["product_id"], 0)
                sd, slt  = r.get("sigma_d", 0), r.get("sigma_lt", 0)
                lt, dp   = r.get("avg_lt", 0), r.get("d_prime", 0)
                ss  = ss_engine.calc_safety_stock(z, pc, lt, sd, dp, slt)
                cy  = op_engine.calc_cycle_stock(dp, pc, lt)
                op  = op_engine.calc_operating_stock(ss["independent"], cy, dp)
                opd = op_engine.calc_operating_stock(ss["dependent"],   cy, dp)
                rows.append({
                    "제품": pname(r.get("product_id", "")), "σd(일)": round(sd, 3),
                    "σLT(일)": round(slt, 2), "평균LT": round(lt, 2), "d'(일)": round(dp, 1),
                    "안전재고(독립)": round(ss["independent"], 1), "안전재고(종속)": round(ss["dependent"], 1),
                    "사이클재고": round(cy, 1),
                    "운영재고(독립)톤": round(op["operating_stock_ton"], 1),
                    "운영재고(독립)일": round(op["operating_stock_days"], 1),
                    "운영재고(종속)톤": round(opd["operating_stock_ton"], 1),
                    "운영재고(종속)일": round(opd["operating_stock_days"], 1),
                })
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.divider()

    # ── 차트 1: 운영재고 막대 ────────────────────────────────────────────────
    scenario     = st.radio("시나리오 선택", ["독립 공식 (Independent)", "종속 공식 (Dependent)"], horizontal=True)
    use_dependent = "종속" in scenario

    st.subheader("📊 제품별 운영재고 비교")
    if not df.empty and "product_id" in df.columns:
        fig1 = go.Figure()
        pids_list  = df["product_id"].tolist()
        names_list = [pname(p) for p in pids_list]
        ind_vals   = df.get("safety_stock_independent", pd.Series([0]*len(df))).tolist()
        dep_vals   = df.get("safety_stock_dependent",   pd.Series([0]*len(df))).tolist()
        cycle_vals = df.get("cycle_stock",              pd.Series([0]*len(df))).tolist()
        fig1.add_bar(name="안전재고(종속)" if use_dependent else "안전재고(독립)",
                     x=names_list, y=dep_vals if use_dependent else ind_vals,
                     marker_color="#FF6B6B" if use_dependent else "#4ECDC4")
        fig1.add_bar(name="사이클재고", x=names_list, y=cycle_vals, marker_color="#45B7D1")
        fig1.update_layout(barmode="stack", title="제품별 운영재고 구성 (톤)",
                           xaxis_title="제품", yaxis_title="재고량 (톤)", height=400)
        st.plotly_chart(fig1, use_container_width=True)

    # ── 차트 2: σd 추세 ──────────────────────────────────────────────────────
    st.subheader("📈 수요편차(σd) 추세 (최근 12개월)")
    selected_sigma = st.multiselect("제품 선택", prod_ids,
                                    default=prod_ids[:3], key="sigma_select",
                                    format_func=pname)
    if selected_sigma:
        fig2 = go.Figure()
        for pid in selected_sigma:
            sales_data  = sorted(_cached_sales(pid, 12), key=lambda r: r["yyyymm"])
            pts, months_pts, buf = [], [], []
            for r in sales_data:
                if r.get("deviation") is not None:
                    buf.append(r["deviation"])
                    if len(buf) >= 3:
                        mean_d = sum(buf) / len(buf)
                        var_d  = sum((x - mean_d)**2 for x in buf) / (len(buf) - 1)
                        pts.append(round(math.sqrt(var_d) / 22, 3))
                        months_pts.append(r["yyyymm"])
            if months_pts:
                fig2.add_scatter(x=months_pts, y=pts, mode="lines+markers", name=pname(pid))
        fig2.update_layout(title="월별 σd 추세 (일 단위)", xaxis_title="월",
                           yaxis_title="σd (톤/일)", height=350)
        st.plotly_chart(fig2, use_container_width=True)

    # ── 차트 3: LT 분포 ──────────────────────────────────────────────────────
    st.subheader("📉 리드타임 분포 (이상치 보정 전/후)")
    selected_lt = st.selectbox("제품 선택", prod_ids, key="lt_dist_select", format_func=pname)
    lt_recs     = _cached_lt(selected_lt, 12)
    if lt_recs:
        raw_lt = [r["lt_days"]    for r in lt_recs]
        adj_lt = [r["lt_adjusted"] for r in lt_recs if r.get("lt_adjusted") is not None]
        fig3   = go.Figure()
        fig3.add_histogram(x=raw_lt, name="보정 전", opacity=0.6, marker_color="#FF6B6B", nbinsx=30)
        fig3.add_histogram(x=adj_lt, name="보정 후", opacity=0.6, marker_color="#4ECDC4", nbinsx=30)
        fig3.update_layout(barmode="overlay", title=f"[{pname(selected_lt)}] 리드타임 분포",
                           xaxis_title="리드타임 (일)", yaxis_title="빈도", height=350)
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("리드타임 데이터가 없습니다.")

    st.divider()

    # ── GDP + ML 참고 패널 ────────────────────────────────────────────────────
    with st.expander("📌 GDP 반영 수요 추정 — 참고용 (운영재고 산출에 미반영)", expanded=False):
        st.info("**이 패널은 참고용입니다.**  \n"
                "한국은행 GDP 성장률을 반영한 ML 수요 추정치를 경영계획과 비교합니다.  \n"
                "실제 운영재고 산출에는 사용되지 않으며, 경영계획 수립 시 참고 자료로 활용하세요.", icon="ℹ️")

        st.markdown("#### 📈 한국은행 GDP 성장률 (분기별)")
        try:
            gdp_disp = _cached_gdp(datetime.now().year)
            gc1, gc2, gc3, gc4, gc5 = st.columns(5)
            gc1.metric("1분기", f"{gdp_disp.get('Q1', '-')}%")
            gc2.metric("2분기", f"{gdp_disp.get('Q2', '-')}%")
            gc3.metric("3분기", f"{gdp_disp.get('Q3', '-')}%")
            gc4.metric("4분기", f"{gdp_disp.get('Q4', '-')}%")
            gc5.metric("연평균", f"{gdp_disp.get('annual', 0):.2f}%")
            src = gdp_disp.get("source", "default")
            src_label = {"ECOS_API": "🟢 한국은행 API (실시간)",
                         "cache":    "🟡 DB 캐시",
                         "default":  "🔴 기본값(2.5%) — API 키 미설정"}.get(src, src)
            st.caption(f"데이터 출처: {src_label}")
            if src == "default":
                st.warning("⚠️ ECOS API 키 미설정. '⚙️ 파라미터 설정'에서 입력하세요.")
        except Exception as e:
            st.error(f"GDP 조회 오류: {e}")

        st.divider()
        st.markdown("#### 🤖 제품별 수요 추정 (GDP 반영 ML 예측 vs 경영계획)")
        if st.button("🔄 전체 제품 ML 추정 실행", key="ml_all_btn"):
            with st.spinner("ML 수요 추정 중..."):
                try:
                    from ml.demand_forecast import DemandForecaster
                    forecaster = DemandForecaster()
                    ml_rows    = []
                    for r in results:
                        pid  = r.get("product_id", "")
                        plan = r.get("d_prime", 1) * 22
                        ref  = forecaster.get_forecast_as_reference(pid, plan)
                        ml_rows.append({
                            "제품": pname(pid), "경영계획(톤)": f"{plan:,.0f}",
                            "ML 추정(톤)": f"{ref.get('ml_forecast', 0):,.0f}",
                            "차이율": f"{ref.get('diff_pct', 0):.1f}%",
                            "사용모델": ref.get("model_used", "-"),
                            "MAPE": f"{ref.get('mape', 0):.1f}%",
                            "GDP(적용값)": f"{ref.get('gdp_used', 2.5):.2f}%",
                            "주의": "⚠️ 10% 초과" if ref.get("flag") else "✅ 정상",
                        })
                    st.dataframe(pd.DataFrame(ml_rows), use_container_width=True, hide_index=True)
                    flagged = [r for r in ml_rows if "⚠️" in r["주의"]]
                    if flagged:
                        st.warning(f"⚠️ {len(flagged)}개 제품 ML 추정과 경영계획 차이 10% 이상.")
                    else:
                        st.success("✅ 전체 제품 ML 추정이 경영계획과 10% 이내.")
                    st.caption("※ ML 추정값은 참고용이며 운영재고 수식(d')에 미반영.")
                except Exception as e:
                    st.error(f"ML 추정 오류: {e}")
                    import traceback; st.code(traceback.format_exc())

    st.divider()

    # ── 연말까지 운영재고 예측 ────────────────────────────────────────────────
    st.subheader("📅 연말까지 월별 운영재고 예측")
    st.caption("σd·σLT는 최근 실적 고정값, 판매량은 EMA/선형회귀(GDP반영)로 월별 추정합니다.")

    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        forecast_sl = st.selectbox("서비스 수준", [0.90, 0.95, 0.99], index=1,
                                   format_func=lambda x: f"{int(x*100)}%", key="forecast_sl")
    with fc2:
        forecast_pids = st.multiselect("조회 지종", [r["product_id"] for r in results],
                                       default=[r["product_id"] for r in results],
                                       key="forecast_products",
                                       format_func=pname)
    with fc3:
        wdays_fc = st.number_input("월 영업일수", value=22, min_value=15, max_value=25, key="fc_wdays")

    if st.button("📊 연말까지 운영재고 예측 실행", type="primary", key="forecast_btn"):
        if not forecast_pids:
            st.warning("조회할 지종을 1개 이상 선택하세요.")
        else:
            with st.spinner(f"{len(forecast_pids)}개 지종 × 연말까지 계산 중..."):
                try:
                    forecast_df, chart_data = _build_forecast(
                        results, forecast_pids, forecast_sl, wdays_fc, name_map
                    )

                    if forecast_df.empty:
                        st.warning("예측 데이터가 없습니다.")
                    else:
                        # 피벗 — 중복 제거 후 생성
                        forecast_df_dedup = forecast_df.drop_duplicates(subset=["지종", "월"])

                        st.markdown("#### 📋 지종별 월별 운영재고 예측표 (톤)")
                        pivot = forecast_df_dedup.pivot(index="지종", columns="월", values="운영재고(톤)")
                        st.dataframe(pivot.style.background_gradient(cmap="YlOrRd", axis=1),
                                     use_container_width=True)

                        st.markdown("#### 📋 지종별 월별 운영재고 예측표 (일수)")
                        pivot_d = forecast_df_dedup.pivot(index="지종", columns="월", values="운영재고(일)")
                        st.dataframe(pivot_d.style.background_gradient(cmap="Blues", axis=1),
                                     use_container_width=True)

                        st.markdown("#### 📈 월별 운영재고 추이 (연말까지)")
                        fig_fc = go.Figure()
                        for pid, pts in chart_data.items():
                            fig_fc.add_scatter(x=[p[0] for p in pts], y=[p[1] for p in pts],
                                               mode="lines+markers", name=pname(pid), line=dict(width=2))
                        fig_fc.update_layout(xaxis_title="월", yaxis_title="운영재고 (톤)",
                                             height=420, hovermode="x unified",
                                             legend=dict(orientation="h", yanchor="bottom", y=1.02))
                        st.plotly_chart(fig_fc, use_container_width=True)

                        with st.expander("🔍 상세 데이터 보기"):
                            st.dataframe(forecast_df, use_container_width=True, hide_index=True)

                        st.caption(f"※ 서비스수준 {int(forecast_sl*100)}% 기준 | "
                                   f"σd·σLT·평균LT 최근 실적 고정 | "
                                   f"판매량 EMA/선형회귀 월별 추정")

                except Exception as e:
                    st.error(f"예측 오류: {e}")
                    import traceback; st.code(traceback.format_exc())

    st.divider()

    # ── 경고 및 권고 ──────────────────────────────────────────────────────────
    st.subheader("🚩 경고 및 권고 사항")
    any_flag = False
    for r in results:
        for flag in r.get("flags", []):
            any_flag = True
            msg = flag.get("message", "")
            if flag.get("level") == "warning":
                st.warning(f"⚠️ [{r.get('product_id')}] {msg}")
            else:
                st.info(f"ℹ️ [{r.get('product_id')}] {msg}")
    if not any_flag:
        st.success("✅ 모든 제품의 산출 결과가 정상입니다.")
