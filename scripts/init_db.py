
import csv
import os
from pathlib import Path

import mysql.connector

BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = BASE_DIR / "sql" / "01_schema.sql"
RAW_DIR = BASE_DIR / "data" / "raw"

FUND_MASTER_CSV = RAW_DIR / "01_fund_master.csv"
SCHEME_PERF_CSV = RAW_DIR / "07_scheme_performance.csv"

MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "fund_screener")


def _run_schema(cur):
   
    script = SCHEMA_PATH.read_text()
    statements = [s.strip() for s in script.split(";") if s.strip()]
    for stmt in statements:
        cur.execute(stmt)


def build_database():
    # Connect without selecting a database yet - the schema script itself
    # contains `CREATE DATABASE IF NOT EXISTS fund_screener;`
    conn = mysql.connector.connect(
        host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD
    )
    cur = conn.cursor()

    # 1. schema (creates the database, tables, view, triggers)
    _run_schema(cur)
    conn.commit()
    cur.execute(f"USE {MYSQL_DATABASE}")

    # 2. funds
    with open(FUND_MASTER_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [
            (
                r["amfi_code"], r["fund_house"], r["scheme_name"], r["category"],
                r["sub_category"], r["plan"], r["launch_date"], r["benchmark"],
                r["expense_ratio_pct"], r["exit_load_pct"], r["min_sip_amount"],
                r["min_lumpsum_amount"], r["fund_manager"], r["risk_category"],
                r["sebi_category_code"],
            )
            for r in reader
        ]
    cur.executemany(
        """INSERT INTO funds (
            amfi_code, fund_house, scheme_name, category, sub_category, plan,
            launch_date, benchmark, expense_ratio_pct, exit_load_pct,
            min_sip_amount, min_lumpsum_amount, fund_manager, risk_category,
            sebi_category_code
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )

    # 3. fund_performance
    with open(SCHEME_PERF_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [
            (
                r["amfi_code"], r["return_1yr_pct"], r["return_3yr_pct"],
                r["return_5yr_pct"], r["benchmark_3yr_pct"], r["alpha"], r["beta"],
                r["sharpe_ratio"], r["sortino_ratio"], r["std_dev_ann_pct"],
                r["max_drawdown_pct"], r["aum_crore"], r["morningstar_rating"],
                r["risk_grade"],
            )
            for r in reader
        ]
    cur.executemany(
        """INSERT INTO fund_performance (
            amfi_code, return_1yr_pct, return_3yr_pct, return_5yr_pct,
            benchmark_3yr_pct, alpha, beta, sharpe_ratio, sortino_ratio,
            std_dev_ann_pct, max_drawdown_pct, aum_crore, morningstar_rating,
            risk_grade
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )

    conn.commit()
    cur.execute("SELECT COUNT(*) FROM funds")
    n_funds = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM fund_performance")
    n_perf = cur.fetchone()[0]
    cur.close()
    conn.close()
    print(f"Database '{MYSQL_DATABASE}' built at {MYSQL_HOST}:{MYSQL_PORT}")
    print(f"  funds:             {n_funds} rows")
    print(f"  fund_performance:  {n_perf} rows")


if __name__ == "__main__":
    build_database()
