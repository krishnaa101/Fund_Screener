-- ============================================================
-- Fund Screener - Core Schema (MySQL 8.0+)
-- Requires MySQL 8.0+ for window functions (PERCENT_RANK) used
-- in the fund_scores view below.
-- ============================================================

CREATE DATABASE IF NOT EXISTS fund_screener;
USE fund_screener;

-- ---------------------------------------------------
-- 1. Fund master data (static attributes of each scheme)
-- ---------------------------------------------------
DROP TABLE IF EXISTS funds;
CREATE TABLE funds (
    amfi_code INT PRIMARY KEY,
    fund_house  VARCHAR(255) NOT NULL,
    scheme_name  VARCHAR(255) NOT NULL,
    category   VARCHAR(20)  NOT NULL,      -- Equity / Debt
    sub_category   VARCHAR(50),                -- Large Cap, Small Cap, Gilt, etc.
    plan          VARCHAR(20),                -- Regular / Direct
    launch_date  DATE,
    benchmark     VARCHAR(255),
    expense_ratio_pct DECIMAL(5,2),
    exit_load_pct    DECIMAL(5,2),
    min_sip_amount    DECIMAL(10,2),
    min_lumpsum_amount    DECIMAL(12,2),
    fund_manager     VARCHAR(255),
    risk_category    VARCHAR(30),                   -- Low / Moderate / Moderately High / High / Very High
    sebi_category_code  VARCHAR(30)
) ENGINE=InnoDB;

-- ---------------------------------------------------
-- 2. Performance & risk metrics per scheme
-- ---------------------------------------------------
DROP TABLE IF EXISTS fund_performance;
CREATE TABLE fund_performance (
    amfi_code           INT PRIMARY KEY,
    return_1yr_pct       DECIMAL(6,2),
    return_3yr_pct       DECIMAL(6,2),
    return_5yr_pct       DECIMAL(6,2),
    benchmark_3yr_pct    DECIMAL(6,2),
    alpha                DECIMAL(6,2),
    beta                 DECIMAL(6,2),
    sharpe_ratio         DECIMAL(6,2),
    sortino_ratio        DECIMAL(6,2),
    std_dev_ann_pct      DECIMAL(6,2),
    max_drawdown_pct     DECIMAL(6,2),
    aum_crore            DECIMAL(12,2),
    morningstar_rating   TINYINT,
    risk_grade           VARCHAR(30),
    CONSTRAINT fk_perf_fund FOREIGN KEY (amfi_code) REFERENCES funds(amfi_code)
) ENGINE=InnoDB;

-- ---------------------------------------------------
-- 3. Risk profile -> allowed risk_category lookup
--    (drives the "risk-profile filtering" feature)
-- ---------------------------------------------------
DROP TABLE IF EXISTS risk_profile_map;
CREATE TABLE risk_profile_map (
    risk_profile            VARCHAR(30) PRIMARY KEY,   -- Conservative / Balanced / Aggressive
    allowed_risk_categories VARCHAR(255) NOT NULL,       -- comma separated, matches funds.risk_category
    description              VARCHAR(255)
) ENGINE=InnoDB;

INSERT INTO risk_profile_map (risk_profile, allowed_risk_categories, description) VALUES
('Conservative', 'Low,Moderate',              'Capital protection first, can tolerate only small swings'),
('Balanced',     'Moderate,Moderately High',   'Comfortable with moderate ups/downs for better long term growth'),
('Aggressive',   'Moderately High,High,Very High', 'Growth focused, can tolerate large short term swings');

-- ---------------------------------------------------
-- 4. Immutable audit trail
--    Every screener call is logged as an append-only row.
--    Tamper-evidence via a SHA-256 hash chain (like a mini
--    blockchain): each row's hash = sha256(prev_hash + row data)
--    computed in the application layer and stored here.
--    Triggers below physically block UPDATE / DELETE on this
--    table at the database level, so even a compromised
--    application cannot silently rewrite history.
-- ---------------------------------------------------
DROP TABLE IF EXISTS audit_log;
CREATE TABLE audit_log (
    audit_id           INT AUTO_INCREMENT PRIMARY KEY,
    request_time_utc    VARCHAR(40) NOT NULL,
    risk_profile         VARCHAR(30),
    category              VARCHAR(20),
    sub_category          VARCHAR(50),
    min_score             DOUBLE,             -- DOUBLE (not DECIMAL) on purpose: it round-trips
                                                -- through Python as a plain float, matching the
                                                -- float used when the row's hash was first computed.
                                                -- A DECIMAL column would come back as Decimal(),
                                                -- which serializes differently and would break the
                                                -- hash-chain verification in app/audit.py.
    top_n                 INT,
    result_count          INT NOT NULL,
    result_amfi_codes    TEXT,                        -- comma separated, for traceability
    prev_hash             CHAR(64) NOT NULL,
    row_hash              CHAR(64) NOT NULL
) ENGINE=InnoDB;

DROP TRIGGER IF EXISTS trg_audit_no_update;
CREATE TRIGGER trg_audit_no_update
BEFORE UPDATE ON audit_log
FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'audit_log is immutable: UPDATE is not permitted';

DROP TRIGGER IF EXISTS trg_audit_no_delete;
CREATE TRIGGER trg_audit_no_delete
BEFORE DELETE ON audit_log
FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'audit_log is immutable: DELETE is not permitted';

-- ---------------------------------------------------
-- 5. Risk-adjusted composite score (the heart of the screener)
--    Built as a VIEW so it is always computed fresh off the
--    latest data - nothing is pre-baked / stale.
--
--    Approach: rank every fund against peers in the SAME
--    category (Equity vs Debt) on 6 metrics using PERCENT_RANK(),
--    then combine those percentiles into one weighted score
--    (0-100). Using percentiles instead of raw numbers avoids
--    unfairly comparing e.g. Debt fund returns to Equity fund
--    returns, and keeps every metric on the same 0-1 scale
--    before weighting.
--
--    Weights (sum to 1.0):
--      Sharpe ratio        0.25   (return per unit of total risk)
--      Sortino ratio        0.15   (return per unit of downside risk)
--      Alpha                 0.15   (excess return vs benchmark)
--      3yr return            0.20   (raw performance)
--      Std deviation          0.15   (lower volatility -> higher score)
--      Max drawdown           0.10   (shallower worst-case fall -> higher score)
-- ---------------------------------------------------
DROP VIEW IF EXISTS fund_scores;
CREATE VIEW fund_scores AS
SELECT
    fu.amfi_code,
    fu.scheme_name,
    fu.fund_house,
    fu.category,
    fu.sub_category,
    fu.plan,
    fu.risk_category,
    fu.expense_ratio_pct,
    fu.fund_manager,
    fp.return_1yr_pct,
    fp.return_3yr_pct,
    fp.return_5yr_pct,
    fp.alpha,
    fp.beta,
    fp.sharpe_ratio,
    fp.sortino_ratio,
    fp.std_dev_ann_pct,
    fp.max_drawdown_pct,
    fp.aum_crore,
    fp.morningstar_rating,
    ROUND(
        (
            PERCENT_RANK() OVER (PARTITION BY fu.category ORDER BY fp.sharpe_ratio)        * 0.25 +
            PERCENT_RANK() OVER (PARTITION BY fu.category ORDER BY fp.sortino_ratio)       * 0.15 +
            PERCENT_RANK() OVER (PARTITION BY fu.category ORDER BY fp.alpha)               * 0.15 +
            PERCENT_RANK() OVER (PARTITION BY fu.category ORDER BY fp.return_3yr_pct)      * 0.20 +
            PERCENT_RANK() OVER (PARTITION BY fu.category ORDER BY fp.std_dev_ann_pct DESC) * 0.15 +
            PERCENT_RANK() OVER (PARTITION BY fu.category ORDER BY fp.max_drawdown_pct)    * 0.10
        ) * 100
    , 2) AS risk_adjusted_score
FROM funds fu
JOIN fund_performance fp ON fu.amfi_code = fp.amfi_code;
