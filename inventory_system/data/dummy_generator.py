"""
Dummy data generator for the inventory management system.
Generates 36 months of sales and lead time records (2023-01 to 2025-12).
Can be run from CLI or called as a function from the settings UI.
"""

import random
import math
from datetime import datetime, timedelta
from data.db import init_db, get_conn

PRODUCTS = [
    # (product_id, pc_days, base_sales, pattern)
    ("A1", 2, 3000, "growth"),
    ("A2", 2, 2800, "growth"),
    ("A3", 2, 3200, "decline"),
    ("B1", 4, 3100, "growth"),
    ("B2", 4, 2900, "growth"),
    ("B3", 4, 3050, "stable"),
    ("C1", 7, 2950, "growth"),
    ("C2", 7, 3100, "growth"),
    ("C3", 7, 2800, "decline"),
    ("C4", 7, 3000, "stable"),
]

LT_PARAMS = {
    2: {"mean": 2.5, "std": 0.5},
    4: {"mean": 4.2, "std": 1.0},
    7: {"mean": 7.1, "std": 1.5},
}

START_YEAR = 2023
START_MONTH = 1
NUM_MONTHS = 36


def _yyyymm(year, month):
    return f"{year}{month:02d}"


def _months_list():
    months = []
    y, m = START_YEAR, START_MONTH
    for _ in range(NUM_MONTHS):
        months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def _noise(rng, scale):
    return rng.gauss(0, scale)


def generate_dummy_data():
    """Generate and insert dummy data into the DB. Clears existing data first."""
    init_db()
    rng = random.Random(42)

    with get_conn() as conn:
        # Clear existing data
        conn.execute("DELETE FROM leadtime_record")
        conn.execute("DELETE FROM monthly_sales")
        print("기존 데이터 삭제 완료")

    months = _months_list()

    for product_id, pc_days, base_sales, pattern in PRODUCTS:
        print(f"  [{product_id}] 판매 데이터 생성 중...")
        lt_params = LT_PARAMS[pc_days]

        for idx, (year, month) in enumerate(months):
            yyyymm = _yyyymm(year, month)

            # Plan quantity based on pattern
            if pattern == "growth":
                plan_qty = base_sales * (1 + 0.003 * idx)
            elif pattern == "decline":
                plan_qty = base_sales * (1 - 0.002 * idx)
            else:
                plan_qty = float(base_sales)

            plan_qty = max(plan_qty, 500.0)  # Floor

            # Actual = plan + deviation (8-15% std)
            noise_pct = rng.uniform(0.08, 0.15)
            deviation = _noise(rng, plan_qty * noise_pct)
            actual_qty = max(plan_qty + deviation, 0.0)

            with get_conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO monthly_sales (product_id, yyyymm, plan_qty, actual_qty, deviation) VALUES (?,?,?,?,?)",
                    (product_id, yyyymm, round(plan_qty, 2), round(actual_qty, 2), round(deviation, 2)),
                )

            # Lead time records: ~3-5 per month
            num_lt = rng.randint(3, 5)
            for lt_idx in range(num_lt):
                # Order date within the month
                day = rng.randint(1, 25)
                order_date = datetime(year, month, day)

                # Inject 5% outliers
                is_fake_outlier = rng.random() < 0.05
                if is_fake_outlier:
                    lt_days = rng.uniform(31, 45)
                else:
                    lt_days = max(0.5, rng.gauss(lt_params["mean"], lt_params["std"]))

                receipt_date = order_date + timedelta(days=lt_days)
                weight_qty = rng.uniform(100, 500)

                order_str = order_date.strftime("%Y-%m-%d")
                receipt_str = receipt_date.strftime("%Y-%m-%d")

                # Determine outlier and adjusted value
                is_outlier = 1 if lt_days > 30 or lt_days < 0 else 0
                lt_adjusted = lt_days
                if is_outlier:
                    lt_adjusted = lt_params["mean"]  # Replace with mean for simplicity

                with get_conn() as conn:
                    conn.execute(
                        """INSERT INTO leadtime_record
                           (product_id, order_date, receipt_date, lt_days, lt_adjusted, is_outlier, weight_qty)
                           VALUES (?,?,?,?,?,?,?)""",
                        (
                            product_id, order_str, receipt_str,
                            round(lt_days, 2), round(lt_adjusted, 2),
                            is_outlier, round(weight_qty, 2),
                        ),
                    )

        print(f"  [{product_id}] 완료")

    print("더미 데이터 생성 완료!")


if __name__ == "__main__":
    generate_dummy_data()
