-- ============================================================
-- Reference screener query (MySQL)
-- This is the exact logic the API runs (see app/crud.py: screen_funds()).
-- Kept here as a plain .sql file so the SQL can be run/explained
-- on its own, outside of FastAPI, e.g. in MySQL Workbench.
--
-- Example: screen for a "Balanced" investor, Equity funds only,
-- minimum score 50, top 10 results.
-- ============================================================

USE fund_screener;

SELECT
    amfi_code,
    scheme_name,
    fund_house,
    category,
    sub_category,
    risk_category,
    sharpe_ratio,
    sortino_ratio,
    alpha,
    return_3yr_pct,
    std_dev_ann_pct,
    max_drawdown_pct,
    morningstar_rating,
    risk_adjusted_score
FROM fund_scores
WHERE category = 'Equity'
  AND risk_category IN ('Moderate', 'Moderately High')   -- from risk_profile_map for 'Balanced'
  AND risk_adjusted_score >= 50
ORDER BY risk_adjusted_score DESC
LIMIT 10;

-- Simpler equivalent (without hardcoding the risk categories above),
-- joining risk_profile_map directly with FIND_IN_SET on its
-- comma-separated allowed_risk_categories column:
--
-- SELECT fs.*
-- FROM fund_scores fs
-- JOIN risk_profile_map rpm ON rpm.risk_profile = 'Balanced'
-- WHERE FIND_IN_SET(fs.risk_category, rpm.allowed_risk_categories) > 0
--   AND fs.category = 'Equity'
--   AND fs.risk_adjusted_score >= 50
-- ORDER BY fs.risk_adjusted_score DESC
-- LIMIT 10;
--
-- What the API actually builds dynamically per request
-- (see app/crud.py), with %s placeholders bound by the driver:
--
-- SELECT * FROM fund_scores
-- WHERE category = %s
--   AND risk_category IN (%s, %s, ...)
--   AND risk_adjusted_score >= %s
-- ORDER BY risk_adjusted_score DESC
-- LIMIT %s;
