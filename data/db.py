import sqlite3
import os
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime

# Streamlit Cloud는 /mount/src/ 가 읽기 전용이므로 쓰기 가능한 경로 선택
_default_db = Path(__file__).parent.parent / "inventory.db"
if os.access(_default_db.parent, os.W_OK):
    DB_PATH = _default_db
else:
    DB_PATH = Path("/tmp") / "inventory.db"

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


@contextmanager
def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        conn.executescript(schema)
        # Insert default products if not present
        products = [
            ("A1", "ACB",      2, "stable", 0.95),
            ("A2", "FSB",      2, "stable", 0.95),
            ("A3", "SC(N)",    2, "stable", 0.95),
            ("B1", "IV",       4, "stable", 0.95),
            ("B2", "SC APR",   4, "stable", 0.95),
            ("B3", "HAPPY",    4, "stable", 0.95),
            ("C1", "AB라이트", 7, "stable", 0.95),
            ("C2", "AB플러스", 7, "stable", 0.95),
            ("C3", "AB더블랑", 7, "stable", 0.95),
            ("C4", "FAB",      7, "stable", 0.95),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO product (product_id, product_name, pc_days, trend, service_level) VALUES (?,?,?,?,?)",
            products,
        )
        for pid, pname, *_ in products:
            conn.execute(
                "UPDATE product SET product_name=? WHERE product_id=?",
                (pname, pid),
            )


def get_products():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM product ORDER BY product_id").fetchall()
        return [dict(r) for r in rows]


def get_monthly_sales(product_id, window_months=36):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM monthly_sales
               WHERE product_id = ?
               ORDER BY yyyymm DESC
               LIMIT ?""",
            (product_id, window_months),
        ).fetchall()
        return [dict(r) for r in rows]


def insert_monthly_sales(product_id, yyyymm, plan_qty, actual_qty):
    deviation = actual_qty - plan_qty if actual_qty is not None else None
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM monthly_sales WHERE product_id=? AND yyyymm=?",
            (product_id, yyyymm),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE monthly_sales SET plan_qty=?, actual_qty=?, deviation=? WHERE product_id=? AND yyyymm=?",
                (plan_qty, actual_qty, deviation, product_id, yyyymm),
            )
        else:
            conn.execute(
                "INSERT INTO monthly_sales (product_id, yyyymm, plan_qty, actual_qty, deviation) VALUES (?,?,?,?,?)",
                (product_id, yyyymm, plan_qty, actual_qty, deviation),
            )


def get_leadtime_records(product_id, window_months=12):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM leadtime_record
               WHERE product_id = ?
               ORDER BY order_date DESC
               LIMIT ?""",
            (product_id, window_months * 5),
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_product(product_id, product_name, pc_days, service_level=0.95):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO product (product_id, product_name, pc_days, service_level)
               VALUES (?,?,?,?)
               ON CONFLICT(product_id) DO UPDATE SET
                 product_name=excluded.product_name,
                 pc_days=excluded.pc_days,
                 service_level=excluded.service_level""",
            (product_id, product_name, pc_days, service_level),
        )


def batch_insert_monthly_sales(records):
    """records: list of (product_id, yyyymm, plan_qty, actual_qty)"""
    with get_conn() as conn:
        for product_id, yyyymm, plan_qty, actual_qty in records:
            plan_qty = plan_qty if plan_qty is not None else 0.0
            deviation = (actual_qty - plan_qty) if actual_qty is not None else None
            conn.execute(
                "DELETE FROM monthly_sales WHERE product_id=? AND yyyymm=?",
                (product_id, yyyymm),
            )
            conn.execute(
                """INSERT INTO monthly_sales (product_id, yyyymm, plan_qty, actual_qty, deviation)
                   VALUES (?,?,?,?,?)""",
                (product_id, yyyymm, plan_qty, actual_qty, deviation),
            )


def batch_insert_leadtime(records):
    """records: list of (product_id, order_date, receipt_date, lt_days)
    Performs batch outlier marking per product after insert."""
    import statistics
    with get_conn() as conn:
        conn.executemany(
            """INSERT INTO leadtime_record
               (product_id, order_date, receipt_date, lt_days, lt_adjusted, is_outlier, weight_qty)
               VALUES (?,?,?,?,?,0,NULL)""",
            [(r[0], r[1], r[2], r[3], r[3]) for r in records],
        )
    # Batch outlier correction per product
    with get_conn() as conn:
        products = conn.execute(
            "SELECT DISTINCT product_id FROM leadtime_record"
        ).fetchall()
    for row in products:
        pid = row["product_id"]
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT id, lt_days FROM leadtime_record WHERE product_id=?", (pid,)
            ).fetchall()
        if len(rows) < 4:
            continue
        vals = [r["lt_days"] for r in rows]
        mean = statistics.mean(vals)
        stdev = statistics.stdev(vals)
        upper = mean + 3 * stdev
        lower = max(0.1, mean - 3 * stdev)
        with get_conn() as conn:
            for r in rows:
                if r["lt_days"] > upper or r["lt_days"] < lower:
                    conn.execute(
                        "UPDATE leadtime_record SET is_outlier=1, lt_adjusted=? WHERE id=?",
                        (mean, r["id"]),
                    )


def insert_leadtime_record(product_id, order_date, receipt_date, lt_days, weight_qty=None):
    from utils.outlier import detect_outlier, correct_outlier

    is_outlier = 1 if detect_outlier(lt_days) else 0
    lt_adjusted = lt_days

    if is_outlier:
        # Get reference values for correction
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT lt_days FROM leadtime_record WHERE product_id=? AND is_outlier=0 ORDER BY order_date DESC LIMIT 30",
                (product_id,),
            ).fetchall()
        ref_values = [r["lt_days"] for r in rows] if rows else [lt_days]
        lt_adjusted, _ = correct_outlier(lt_days, ref_values)

    with get_conn() as conn:
        conn.execute(
            """INSERT INTO leadtime_record
               (product_id, order_date, receipt_date, lt_days, lt_adjusted, is_outlier, weight_qty)
               VALUES (?,?,?,?,?,?,?)""",
            (product_id, order_date, receipt_date, lt_days, lt_adjusted, is_outlier, weight_qty),
        )


def save_stock_result(result_dict):
    keys = [
        "product_id", "calc_yyyymm", "target_yyyymm", "service_level",
        "z_value", "sigma_d", "sigma_lt", "avg_lt", "d_prime",
        "safety_stock_independent", "safety_stock_dependent",
        "cycle_stock", "operating_stock", "operating_days",
    ]
    values = [result_dict.get(k) for k in keys]
    with get_conn() as conn:
        # 동일 산출월·대상월·제품·서비스수준 기존 레코드 삭제 후 재삽입 (중복 방지)
        conn.execute(
            """DELETE FROM stock_result
               WHERE product_id=? AND calc_yyyymm=? AND target_yyyymm=? AND service_level=?""",
            (result_dict.get("product_id"), result_dict.get("calc_yyyymm"),
             result_dict.get("target_yyyymm"), result_dict.get("service_level")),
        )
        conn.execute(
            f"""INSERT INTO stock_result ({','.join(keys)}) VALUES ({','.join(['?']*len(keys))})""",
            values,
        )


def get_stock_results(product_id=None, limit=100):
    with get_conn() as conn:
        if product_id:
            rows = conn.execute(
                "SELECT * FROM stock_result WHERE product_id=? ORDER BY calc_yyyymm DESC LIMIT ?",
                (product_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM stock_result ORDER BY calc_yyyymm DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def get_setting(key, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key, value):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?,?)",
            (key, str(value)),
        )


def get_macro_indicator(indicator, period):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM macro_indicator WHERE indicator=? AND period=?",
            (indicator, period),
        ).fetchone()
        return dict(row) if row else None


def save_macro_indicator(indicator, period, value, source):
    fetched_at = datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO macro_indicator (indicator, period, value, source, fetched_at)
               VALUES (?,?,?,?,?)
               ON CONFLICT(indicator, period) DO UPDATE SET value=excluded.value, source=excluded.source, fetched_at=excluded.fetched_at""",
            (indicator, period, value, source, fetched_at),
        )
