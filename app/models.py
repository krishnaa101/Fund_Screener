from typing import Optional, List
from pydantic import BaseModel, Field


class FundScore(BaseModel):
    amfi_code: int
    scheme_name: str
    fund_house: str
    category: str
    sub_category: Optional[str] = None
    risk_category: Optional[str] = None
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    alpha: Optional[float] = None
    return_3yr_pct: Optional[float] = None
    std_dev_ann_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    morningstar_rating: Optional[int] = None
    risk_adjusted_score: float


class FundDetail(FundScore):
    plan: Optional[str] = None
    expense_ratio_pct: Optional[float] = None
    fund_manager: Optional[str] = None
    return_1yr_pct: Optional[float] = None
    return_5yr_pct: Optional[float] = None
    beta: Optional[float] = None
    aum_crore: Optional[float] = None


class ScreenResponse(BaseModel):
    filters_applied: dict
    result_count: int
    audit_id: int
    results: List[FundScore]


class RiskProfile(BaseModel):
    risk_profile: str
    allowed_risk_categories: str
    description: Optional[str] = None


class AuditLogEntry(BaseModel):
    audit_id: int
    request_time_utc: str
    risk_profile: Optional[str] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None
    min_score: Optional[float] = None
    top_n: Optional[int] = None
    result_count: int
    result_amfi_codes: Optional[str] = None
    prev_hash: str
    row_hash: str


class AuditVerifyResponse(BaseModel):
    valid: bool
    rows_checked: int
    broken_at_audit_id: Optional[int] = Field(
        default=None,
        description="First audit_id where the hash chain no longer matches, if any",
    )
    message: str
