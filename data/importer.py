import pandas as pd
from data.db import upsert_product, batch_insert_monthly_sales, batch_insert_leadtime


def _ym_to_yyyymm(ym_val):
    """'23.01' or '23.1' → '202301'"""
    s = str(ym_val).strip()
    if "." in s:
        yr, mo = s.split(".", 1)
        return f"{2000 + int(yr)}{int(mo):02d}"
    return s


def import_backdata_excel(filepath, plan_year=2026):
    """
    판매량실적추정·리드타임·판매계획 시트가 포함된 Excel을 파싱해 DB에 적재.
    Returns: dict with counts
    """
    xl = pd.ExcelFile(filepath)

    required = {"판매량실적추정", "리드타임", "판매계획"}
    missing = required - set(xl.sheet_names)
    if missing:
        raise ValueError(f"필수 시트 누락: {missing}")

    # ── 1. 판매계획 → products + 2026 plan_qty ────────────────────────
    # cols: [0]팀명 [1]지종코드(BW) [2]지종명 [3]생산주기(일) [4-15]01월~12월 [16]Grand Total
    df_plan = xl.parse("판매계획")
    month_cols = [f"{m:02d}월" for m in range(1, 13)]

    pc_map = {}       # 지종명 → pc_days
    plan_agg = {}     # (지종명, yyyymm) → total plan_qty

    for _, row in df_plan.iterrows():
        pname = row.iloc[2]
        if pd.isna(pname):
            continue
        pname = str(pname).strip()
        if not pname or pname in ("Grand Total", "합계"):
            continue

        pc = int(row.iloc[3]) if pd.notna(row.iloc[3]) else 30
        if pname not in pc_map:
            pc_map[pname] = pc

        for m, col in enumerate(month_cols, 1):
            if col not in df_plan.columns:
                continue
            qty = row[col]
            if pd.notna(qty) and float(qty) > 0:
                yyyymm = f"{plan_year}{m:02d}"
                key = (pname, yyyymm)
                plan_agg[key] = plan_agg.get(key, 0.0) + float(qty)

    # ── 2. 판매량실적추정 → actual_qty (실적) + estimate plan_qty (추정) ──
    # cols: [0]구분 [1]년월 [2]팀구분 [3]플랜트 [4]팀명 [5]지종그룹 [6]지종코드 [7]지종명 [8]수량
    df_sales = xl.parse("판매량실적추정")

    actual_agg = {}   # (지종명, yyyymm) → qty
    est_plan_agg = {} # (지종명, yyyymm) → qty

    for _, row in df_sales.iterrows():
        구분 = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        pname = str(row.iloc[7]).strip() if pd.notna(row.iloc[7]) else ""
        ym_val = row.iloc[1]
        qty = row.iloc[8]

        if not pname or pd.isna(qty) or pd.isna(ym_val):
            continue

        yyyymm = _ym_to_yyyymm(ym_val)
        qty = float(qty)
        key = (pname, yyyymm)

        if 구분 == "실적":
            actual_agg[key] = actual_agg.get(key, 0.0) + qty
        else:
            est_plan_agg[key] = est_plan_agg.get(key, 0.0) + qty

    # ── 3. 리드타임 → 주문별 LT records ────────────────────────────────
    # cols: [0]PLANT [1]영업팀 [2]지종그룹 [3]주문번호+품목 [4]지종명
    #       [5]입고일자 [6]출고일자 [7]리드타임 [8]SAP리드타임 ...
    df_lt = xl.parse("리드타임")

    lt_records = []
    for _, row in df_lt.iterrows():
        pname = str(row.iloc[4]).strip() if pd.notna(row.iloc[4]) else ""
        if not pname or pname not in pc_map:
            continue
        order_date = str(row.iloc[5])[:10] if pd.notna(row.iloc[5]) else None
        receipt_date = str(row.iloc[6])[:10] if pd.notna(row.iloc[6]) else None
        lt_days = float(row.iloc[7]) if pd.notna(row.iloc[7]) else None

        if not order_date or lt_days is None or lt_days <= 0:
            continue
        lt_records.append((pname, order_date, receipt_date or order_date, lt_days))

    # ── 4. DB 저장 ────────────────────────────────────────────────────

    # 4a. Products
    for pname, pc in pc_map.items():
        upsert_product(pname, pname, pc)

    # 4b. Monthly sales — 모든 월 통합 (plan + actual)
    all_keys = set(plan_agg) | set(actual_agg) | set(est_plan_agg)
    sales_records = []
    for key in all_keys:
        pname, yyyymm = key
        if pname not in pc_map:
            continue
        # plan: 판매계획 우선, 없으면 추정계획
        plan_qty = plan_agg.get(key) or est_plan_agg.get(key, 0.0)
        actual_qty = actual_agg.get(key)
        sales_records.append((pname, yyyymm, plan_qty, actual_qty))

    batch_insert_monthly_sales(sales_records)

    # 4c. Leadtime records
    batch_insert_leadtime(lt_records)

    return {
        "products": len(pc_map),
        "sales_months": len(sales_records),
        "leadtime_records": len(lt_records),
    }
