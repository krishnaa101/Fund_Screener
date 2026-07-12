"""
Mutual Fund Screener API
Run with:  uvicorn app.main:app --reload
"""
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.database import get_connection
from app import crud, audit
from app.models import (
    FundScore, FundDetail, ScreenResponse, RiskProfile,
    AuditLogEntry, AuditVerifyResponse,
)

app = FastAPI(
    title="Mutual Fund Screener API",
    description=(
        "A simple SQL-driven fund screener built on top of a mutual fund "
        "analytics dataset. Screens funds using a risk-adjusted composite "
        "score, filters by investor risk profile, and keeps a tamper-evident "
        "audit trail of every screen request. Student / portfolio project."
    ),
    version="1.0.0",
)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.get("/risk-profiles", response_model=list[RiskProfile], tags=["meta"])
def list_risk_profiles():
    """Returns the risk-profile -> risk-category mapping used for filtering."""
    with get_connection() as conn:
        rows = crud.get_risk_profiles(conn)
        return [dict(r) for r in rows]


@app.get("/screen", response_model=ScreenResponse, tags=["screener"])
def screen_funds(
    risk_profile: Optional[str] = Query(
        None, description="Conservative | Balanced | Aggressive (see /risk-profiles)"
    ),
    category: Optional[str] = Query(None, description="Equity | Debt"),
    sub_category: Optional[str] = Query(
        None, description="e.g. Large Cap, Small Cap, Flexi Cap, Gilt, Liquid ..."
    ),
    min_score: Optional[float] = Query(
        None, ge=0, le=100, description="Minimum risk_adjusted_score (0-100)"
    ),
    top_n: int = Query(10, ge=1, le=100, description="Max number of funds to return"),
):
    with get_connection() as conn:
        if risk_profile:
            allowed = crud.get_allowed_risk_categories(conn, risk_profile)
            if not allowed:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown risk_profile '{risk_profile}'. "
                           f"See /risk-profiles for valid values.",
                )

        rows = crud.screen_funds(
            conn, risk_profile, category, sub_category, min_score, top_n
        )
        results = [dict(r) for r in rows]
        amfi_codes = [r["amfi_code"] for r in results]

        audit_id = audit.write_audit_log(
            conn, risk_profile, category, sub_category, min_score, top_n, amfi_codes
        )

        return {
            "filters_applied": {
                "risk_profile": risk_profile,
                "category": category,
                "sub_category": sub_category,
                "min_score": min_score,
                "top_n": top_n,
            },
            "result_count": len(results),
            "audit_id": audit_id,
            "results": results,
        }


@app.get("/funds/{amfi_code}", response_model=FundDetail, tags=["screener"])
def get_fund(amfi_code: int):
    """Full detail + risk-adjusted score for a single fund by AMFI code."""
    with get_connection() as conn:
        row = crud.get_fund_by_code(conn, amfi_code)
        if row is None:
            raise HTTPException(status_code=404, detail="Fund not found")
        return dict(row)


@app.get("/audit/logs", response_model=list[AuditLogEntry], tags=["audit"])
def get_audit_logs(limit: int = Query(50, ge=1, le=500)):
    """Most recent screen requests, newest first. Rows here can only ever
    be appended - see the trg_audit_no_update / trg_audit_no_delete
    triggers in sql/01_schema.sql."""
    with get_connection() as conn:
        rows = crud.get_audit_logs(conn, limit)
        return [dict(r) for r in rows]


@app.get("/audit/verify", response_model=AuditVerifyResponse, tags=["audit"])
def verify_audit_chain():
    """Recomputes the SHA-256 hash chain over the entire audit_log table
    and confirms nothing has been altered since it was written."""
    with get_connection() as conn:
        return audit.verify_chain(conn)
