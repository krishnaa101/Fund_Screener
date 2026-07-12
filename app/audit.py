
import hashlib
import json
from datetime import datetime, timezone

from mysql.connector.connection import MySQLConnection

GENESIS_HASH = "0" * 64


def _compute_row_hash(prev_hash: str, payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()


def write_audit_log(
    conn: MySQLConnection,
    risk_profile: str | None,
    category: str | None,
    sub_category: str | None,
    min_score: float | None,
    top_n: int | None,
    result_amfi_codes: list[int],
) -> int:
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT row_hash FROM audit_log ORDER BY audit_id DESC LIMIT 1")
    last = cur.fetchone()
    prev_hash = last["row_hash"] if last else GENESIS_HASH

    request_time_utc = datetime.now(timezone.utc).isoformat()
    payload = {
        "request_time_utc": request_time_utc,
        "risk_profile": risk_profile,
        "category": category,
        "sub_category": sub_category,
        "min_score": min_score,
        "top_n": top_n,
        "result_count": len(result_amfi_codes),
        "result_amfi_codes": ",".join(map(str, result_amfi_codes)),
    }
    row_hash = _compute_row_hash(prev_hash, payload)

    cur.execute(
        """INSERT INTO audit_log (
            request_time_utc, risk_profile, category, sub_category,
            min_score, top_n, result_count, result_amfi_codes,
            prev_hash, row_hash
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            payload["request_time_utc"], risk_profile, category, sub_category,
            min_score, top_n, payload["result_count"], payload["result_amfi_codes"],
            prev_hash, row_hash,
        ),
    )
    conn.commit()
    audit_id = cur.lastrowid
    cur.close()
    return audit_id


def verify_chain(conn: MySQLConnection) -> dict:

    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM audit_log ORDER BY audit_id ASC")
    rows = cur.fetchall()
    cur.close()

    expected_prev = GENESIS_HASH
    for row in rows:
        payload = {
            "request_time_utc": row["request_time_utc"],
            "risk_profile": row["risk_profile"],
            "category": row["category"],
            "sub_category": row["sub_category"],
            "min_score": row["min_score"],
            "top_n": row["top_n"],
            "result_count": row["result_count"],
            "result_amfi_codes": row["result_amfi_codes"],
        }
        if row["prev_hash"] != expected_prev:
            return {
                "valid": False,
                "rows_checked": len(rows),
                "broken_at_audit_id": row["audit_id"],
                "message": f"prev_hash mismatch at audit_id={row['audit_id']} "
                           f"- chain link broken (row deleted/reordered?)",
            }
        recomputed = _compute_row_hash(expected_prev, payload)
        if recomputed != row["row_hash"]:
            return {
                "valid": False,
                "rows_checked": len(rows),
                "broken_at_audit_id": row["audit_id"],
                "message": f"row_hash mismatch at audit_id={row['audit_id']} "
                           f"- row data was modified after being written",
            }
        expected_prev = row["row_hash"]

    return {
        "valid": True,
        "rows_checked": len(rows),
        "broken_at_audit_id": None,
        "message": "Audit chain intact: all rows verified, no tampering detected.",
    }
