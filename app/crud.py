from typing import Optional

from mysql.connector.connection import MySQLConnection


def get_risk_profiles(conn: MySQLConnection):
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM risk_profile_map")
    rows = cur.fetchall()
    cur.close()
    return rows


def get_allowed_risk_categories(conn: MySQLConnection, risk_profile: str) -> list[str]:
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT allowed_risk_categories FROM risk_profile_map WHERE risk_profile = %s",
        (risk_profile,),
    )
    row = cur.fetchone()
    cur.close()
    if row is None:
        return []
    return row["allowed_risk_categories"].split(",")


def screen_funds(
    conn: MySQLConnection,
    risk_profile: Optional[str],
    category: Optional[str],
    sub_category: Optional[str],
    min_score: Optional[float],
    top_n: int,
):
    conditions = []
    params: list = []

    if risk_profile:
        allowed = get_allowed_risk_categories(conn, risk_profile)
        if not allowed:
            return []  # unknown risk profile -> no matches
        placeholders = ",".join("%s" for _ in allowed)
        conditions.append(f"risk_category IN ({placeholders})")
        params.extend(allowed)

    if category:
        conditions.append("category = %s")
        params.append(category)

    if sub_category:
        conditions.append("sub_category = %s")
        params.append(sub_category)

    if min_score is not None:
        conditions.append("risk_adjusted_score >= %s")
        params.append(min_score)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        SELECT *
        FROM fund_scores
        {where_clause}
        ORDER BY risk_adjusted_score DESC
        LIMIT %s
    """
    params.append(top_n)

    cur = conn.cursor(dictionary=True)
    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def get_fund_by_code(conn: MySQLConnection, amfi_code: int):
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM fund_scores WHERE amfi_code = %s", (amfi_code,))
    row = cur.fetchone()
    cur.close()
    return row


def get_audit_logs(conn: MySQLConnection, limit: int = 50):
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM audit_log ORDER BY audit_id DESC LIMIT %s", (limit,))
    rows = cur.fetchall()
    cur.close()
    return rows
