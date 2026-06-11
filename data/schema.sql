CREATE TABLE IF NOT EXISTS product (
    product_id   TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    pc_days      INTEGER NOT NULL,
    trend        TEXT DEFAULT 'stable',
    service_level REAL DEFAULT 0.95
);

CREATE TABLE IF NOT EXISTS monthly_sales (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id   TEXT NOT NULL,
    yyyymm       TEXT NOT NULL,
    plan_qty     REAL NOT NULL,
    actual_qty   REAL,
    deviation    REAL,
    FOREIGN KEY (product_id) REFERENCES product(product_id)
);

CREATE TABLE IF NOT EXISTS leadtime_record (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id   TEXT NOT NULL,
    order_date   TEXT NOT NULL,
    receipt_date TEXT NOT NULL,
    lt_days      REAL NOT NULL,
    lt_adjusted  REAL,
    is_outlier   INTEGER DEFAULT 0,
    weight_qty   REAL,
    FOREIGN KEY (product_id) REFERENCES product(product_id)
);

CREATE TABLE IF NOT EXISTS stock_result (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      TEXT NOT NULL,
    calc_yyyymm     TEXT NOT NULL,
    target_yyyymm   TEXT NOT NULL,
    service_level   REAL NOT NULL,
    z_value         REAL NOT NULL,
    sigma_d         REAL NOT NULL,
    sigma_lt        REAL NOT NULL,
    avg_lt          REAL NOT NULL,
    d_prime         REAL NOT NULL,
    safety_stock_independent  REAL,
    safety_stock_dependent    REAL,
    cycle_stock     REAL NOT NULL,
    operating_stock REAL NOT NULL,
    operating_days  REAL NOT NULL,
    FOREIGN KEY (product_id) REFERENCES product(product_id)
);

CREATE TABLE IF NOT EXISTS macro_indicator (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    indicator    TEXT NOT NULL,
    period       TEXT NOT NULL,
    value        REAL NOT NULL,
    source       TEXT NOT NULL,
    fetched_at   TEXT NOT NULL,
    UNIQUE (indicator, period)
);

CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
