import re
from datetime import datetime


def validate_sales_input(data):
    """
    Validate monthly sales input dict.
    Expected keys: product_id, yyyymm, plan_qty, actual_qty (optional)
    Returns (is_valid, error_messages).
    """
    errors = []

    if not data.get("product_id"):
        errors.append("product_id는 필수 항목입니다.")

    yyyymm = data.get("yyyymm", "")
    if not re.match(r"^\d{6}$", str(yyyymm)):
        errors.append(f"yyyymm 형식이 올바르지 않습니다: '{yyyymm}' (예: 202501)")
    else:
        try:
            year = int(str(yyyymm)[:4])
            month = int(str(yyyymm)[4:])
            if not (2000 <= year <= 2100) or not (1 <= month <= 12):
                errors.append(f"yyyymm 범위가 올바르지 않습니다: {yyyymm}")
        except ValueError:
            errors.append(f"yyyymm 변환 오류: {yyyymm}")

    plan_qty = data.get("plan_qty")
    if plan_qty is None:
        errors.append("plan_qty는 필수 항목입니다.")
    else:
        try:
            if float(plan_qty) < 0:
                errors.append("plan_qty는 0 이상이어야 합니다.")
        except (TypeError, ValueError):
            errors.append("plan_qty는 숫자여야 합니다.")

    actual_qty = data.get("actual_qty")
    if actual_qty is not None:
        try:
            if float(actual_qty) < 0:
                errors.append("actual_qty는 0 이상이어야 합니다.")
        except (TypeError, ValueError):
            errors.append("actual_qty는 숫자여야 합니다.")

    return len(errors) == 0, errors


def validate_leadtime_input(data):
    """
    Validate lead time record input dict.
    Expected keys: product_id, order_date, receipt_date, lt_days, weight_qty (optional)
    Returns (is_valid, error_messages).
    """
    errors = []

    if not data.get("product_id"):
        errors.append("product_id는 필수 항목입니다.")

    for date_field in ["order_date", "receipt_date"]:
        date_val = data.get(date_field, "")
        if not date_val:
            errors.append(f"{date_field}는 필수 항목입니다.")
        else:
            try:
                datetime.strptime(str(date_val), "%Y-%m-%d")
            except ValueError:
                errors.append(f"{date_field} 형식이 올바르지 않습니다: '{date_val}' (예: 2025-01-15)")

    lt_days = data.get("lt_days")
    if lt_days is None:
        errors.append("lt_days는 필수 항목입니다.")
    else:
        try:
            lt_val = float(lt_days)
            if lt_val < 0:
                errors.append("lt_days는 0 이상이어야 합니다.")
        except (TypeError, ValueError):
            errors.append("lt_days는 숫자여야 합니다.")

    weight_qty = data.get("weight_qty")
    if weight_qty is not None:
        try:
            if float(weight_qty) <= 0:
                errors.append("weight_qty는 양수여야 합니다.")
        except (TypeError, ValueError):
            errors.append("weight_qty는 숫자여야 합니다.")

    # Cross-check dates
    order_date = data.get("order_date", "")
    receipt_date = data.get("receipt_date", "")
    if order_date and receipt_date:
        try:
            od = datetime.strptime(order_date, "%Y-%m-%d")
            rd = datetime.strptime(receipt_date, "%Y-%m-%d")
            if rd < od:
                errors.append("receipt_date는 order_date 이후여야 합니다.")
        except ValueError:
            pass  # Already reported above

    return len(errors) == 0, errors
