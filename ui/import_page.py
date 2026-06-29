import os
import tempfile
import streamlit as st
import pandas as pd


def render_import_page():
    st.title("📂 백데이터 가져오기")
    st.caption(
        "판매량실적추정·리드타임·판매계획 시트가 포함된 Excel 파일을 업로드하면 "
        "지종·판매실적·리드타임 데이터를 DB에 일괄 적재합니다."
    )

    st.info(
        "**필수 시트:** 판매량실적추정 · 리드타임 · 판매계획\n\n"
        "- **판매량실적추정**: 지종별 월별 실적/추정 수량 (2023~)\n"
        "- **리드타임**: 주문별 리드타임 실적\n"
        "- **판매계획**: 지종별 월별 판매계획 및 생산주기",
        icon="ℹ️",
    )

    uploaded = st.file_uploader("Excel 파일 업로드 (.xlsx)", type=["xlsx"])
    if not uploaded:
        return

    # 시트 확인
    try:
        xl = pd.ExcelFile(uploaded)
    except Exception as e:
        st.error(f"파일 읽기 오류: {e}")
        return

    required = {"판매량실적추정", "리드타임", "판매계획"}
    missing = required - set(xl.sheet_names)
    if missing:
        st.error(f"❌ 필수 시트 누락: {', '.join(missing)}")
        st.caption(f"파일 내 시트: {', '.join(xl.sheet_names)}")
        return

    st.success(f"✅ 필수 시트 확인 완료: {', '.join(xl.sheet_names)}")

    # ── 데이터 미리보기 ────────────────────────────────────────────────
    with st.expander("📋 데이터 미리보기 (각 시트 상위 5행)"):
        for sheet in ["판매계획", "판매량실적추정", "리드타임"]:
            st.markdown(f"**{sheet}**")
            st.dataframe(xl.parse(sheet, nrows=5), use_container_width=True, hide_index=True)

    # ── 설정 ──────────────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        plan_year = st.number_input(
            "판매계획 연도", value=2026, min_value=2020, max_value=2030,
            help="판매계획 시트의 01월~12월이 해당하는 연도"
        )
    with col2:
        st.markdown("")
        st.markdown("")
        st.caption(f"선택된 연도: **{plan_year}년** 계획이 DB에 plan_qty로 저장됩니다.")

    # ── 규모 예측 ──────────────────────────────────────────────────────
    try:
        n_products = xl.parse("판매계획").iloc[:, 2].nunique()
        n_sales = len(xl.parse("판매량실적추정"))
        n_lt = len(xl.parse("리드타임"))
        c1, c2, c3 = st.columns(3)
        c1.metric("지종 수 (판매계획 기준)", f"{n_products}개")
        c2.metric("판매실적 행수", f"{n_sales:,}행")
        c3.metric("리드타임 행수", f"{n_lt:,}행")
    except Exception:
        pass

    st.divider()

    # ── 가져오기 실행 ──────────────────────────────────────────────────
    if st.button("📥 DB에 가져오기", type="primary", use_container_width=True):
        with st.spinner("데이터 처리 중... (리드타임 건수가 많으면 1~2분 소요될 수 있습니다)"):
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                    tmp.write(uploaded.getvalue())
                    tmp_path = tmp.name

                from data.importer import import_backdata_excel
                result = import_backdata_excel(tmp_path, plan_year=int(plan_year))

                st.success("✅ 가져오기 완료!")
                r1, r2, r3 = st.columns(3)
                r1.metric("등록된 지종", f"{result['products']}개")
                r2.metric("판매 실적/계획", f"{result['sales_months']:,}건")
                r3.metric("리드타임 레코드", f"{result['leadtime_records']:,}건")

                st.info(
                    "데이터 적재가 완료됐습니다.\n\n"
                    "➡️ **월별 실적 입력** 페이지에서 대상월과 영업일수를 설정하고 "
                    "**운영재고 산출 실행** 버튼을 누르세요.",
                    icon="➡️",
                )
                st.cache_data.clear()

            except Exception as e:
                import traceback
                st.error(f"오류 발생: {e}")
                st.code(traceback.format_exc())
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
