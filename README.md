# Fund Screener API

A small SQL-based mutual fund screener, built on top of the datasets from the
Mutual Fund Analytics Platform project. Backend only — FastAPI + MySQL,
explored through the auto-generated Swagger UI (no separate frontend).

Three things it does:

1. **Risk-adjusted scoring** — ranks funds using a composite score computed
   in SQL (window functions), not just raw returns.
2. **Risk-profile filtering** — maps an investor type (Conservative /
   Balanced / Aggressive) to the fund risk categories they should actually
   be shown.
3. **Immutable audit trail** — every screen request is logged as an
   append-only, hash-chained row so the request history can't be silently
   edited later.

---

## Why this exists

The main analytics project (parent folder) was all exploratory — notebooks,
charts, insights. This is the natural next step: turn two of those cleaned
datasets (`01_fund_master.csv`, `07_scheme_performance.csv`) into something
queryable — "show me the best funds *for someone like me*", with a bit of
rigor around how "best" is defined and a paper trail of who asked what.

## How it's built

```
fund_screener/
├── data/raw/                    01_fund_master.csv, 07_scheme_performance.csv
│                                 (copied from the parent project, untouched)
├── sql/
│   ├── 01_schema.sql             tables + the scoring VIEW + audit triggers
│   └── 02_screener_query.sql     the screener query on its own, to read/run directly
├── scripts/
│   └── init_db.py                builds the `fund_screener` MySQL database from the CSVs + schema
├── app/
│   ├── database.py                MySQL connection (auto-builds the database on first run)
│   ├── models.py                  pydantic request/response schemas
│   ├── crud.py                    query builder for /screen
│   ├── audit.py                   hash-chain logic for the audit trail
│   └── main.py                    FastAPI app + all routes
└── requirements.txt
```

### 1. Risk-adjusted score

Comparing a Debt fund's raw return to an Equity fund's raw return isn't
meaningful, so instead of raw numbers, every fund gets ranked **against
its own category** (Equity vs Debt) on six metrics using MySQL's
`PERCENT_RANK()` window function (MySQL 8.0+) — this turns every metric
into a 0–1 percentile, so they're all on the same scale before combining:

| Metric              | Weight | Why                                   |
|----------------------|--------|----------------------------------------|
| Sharpe ratio          | 25%    | return per unit of total risk           |
| Sortino ratio          | 15%    | return per unit of *downside* risk      |
| Alpha                   | 15%    | excess return vs its benchmark          |
| 3-year return             | 20%    | raw performance                         |
| Std deviation (inverted)   | 15%    | lower volatility → higher score         |
| Max drawdown (inverted)      | 10%    | shallower worst-case fall → higher score |

```sql
ROUND((
  PERCENT_RANK() OVER (PARTITION BY category ORDER BY sharpe_ratio)         * 0.25 +
  PERCENT_RANK() OVER (PARTITION BY category ORDER BY sortino_ratio)        * 0.15 +
  PERCENT_RANK() OVER (PARTITION BY category ORDER BY alpha)                * 0.15 +
  PERCENT_RANK() OVER (PARTITION BY category ORDER BY return_3yr_pct)       * 0.20 +
  PERCENT_RANK() OVER (PARTITION BY category ORDER BY std_dev_ann_pct DESC) * 0.15 +
  PERCENT_RANK() OVER (PARTITION BY category ORDER BY max_drawdown_pct)     * 0.10
) * 100, 2) AS risk_adjusted_score
```

This lives in `fund_scores`, a SQL **view** — so it's always computed fresh
off whatever is in the tables, nothing is pre-calculated/stale.

The weights are just a reasonable starting point I picked, not something
derived statistically — easy to justify in an interview as "Sharpe/Sortino
carry the most weight because they're the standard risk-adjusted return
measures; raw return still matters but less than risk-adjusted metrics;
volatility and drawdown are penalties."

### 2. Risk-profile filtering

`risk_profile_map` is a lookup table:

| risk_profile  | allowed risk_category            |
|---------------|-----------------------------------|
| Conservative   | Low, Moderate                       |
| Balanced        | Moderate, Moderately High             |
| Aggressive       | Moderately High, High, Very High        |

`/screen?risk_profile=Balanced` translates to `WHERE risk_category IN
('Moderate','Moderately High')` under the hood — an Aggressive investor
never even sees Low-risk debt funds cluttering their results, and a
Conservative investor never sees Very High risk small-caps.

### 3. Immutable audit trail

Every call to `/screen` appends one row to `audit_log`: who asked for what,
when, and which funds came back. Two layers of protection:

- **Database level**: `audit_log` has `BEFORE UPDATE` / `BEFORE DELETE`
  triggers that `SIGNAL SQLSTATE '45000'` — so even direct SQL against the
  table (e.g. from a MySQL client, bypassing the API entirely) can't modify
  or remove a row.
- **Hash chain**: each row stores `row_hash = sha256(prev_hash + row data)`,
  same idea as a (very small, single-table) blockchain. Since every hash
  depends on the one before it, editing a past row's data directly (e.g. via
  raw access to the database files, bypassing the app/triggers entirely)
  still breaks the chain for every row after it. `GET /audit/verify`
  recomputes the whole chain from scratch and reports the first row where
  it no longer matches.

This was the part I found genuinely interesting to build — it's a small
example of "tamper-evident" vs "tamper-proof": nothing here stops someone
with raw filesystem/database access from editing bytes directly, but it
guarantees that tampering is *detectable* rather than silent.

---

## Running it

Requires a MySQL 8.0+ server (window functions in `fund_scores` need 8.0+)
running and reachable. Connection settings are read from environment
variables, all optional — defaults assume a local server with a passwordless
`root` user:

| Variable          | Default         |
|--------------------|-----------------|
| `MYSQL_HOST`         | `localhost`       |
| `MYSQL_PORT`           | `3306`              |
| `MYSQL_USER`             | `root`                |
| `MYSQL_PASSWORD`          | *(empty)*                |
| `MYSQL_DATABASE`            | `fund_screener`            |

```bash
cd fund_screener
pip install -r requirements.txt

# only needed if your MySQL user/password differ from the defaults above
export MYSQL_USER=root
export MYSQL_PASSWORD=yourpassword

uvicorn app.main:app --reload
```

Then open **http://127.0.0.1:8000/docs** for the Swagger UI.

The `fund_screener` database is created and populated automatically from the
CSVs in `data/raw/` the first time the app starts (it just needs a MySQL
server to already be running) — no manual setup step beyond that. To rebuild
it from scratch at any point: `python scripts/init_db.py`.

## Endpoints

| Method | Path                | What                                                   |
|--------|----------------------|----------------------------------------------------------|
| GET    | `/risk-profiles`       | list the 3 risk profiles and what they map to             |
| GET    | `/screen`               | the screener — filter by risk profile/category/min score, ranked by score |
| GET    | `/funds/{amfi_code}`      | full detail + score for one fund                           |
| GET    | `/audit/logs`             | recent screen requests, newest first                        |
| GET    | `/audit/verify`             | recompute the hash chain, confirm nothing's been tampered with |
| GET    | `/health`                     | liveness check                                                |

Example:

```
GET /screen?risk_profile=Balanced&category=Equity&min_score=60&top_n=5
```

## Notes / things I'd say out loud in an interview

- Uses **MySQL** to match the database already used across the rest of the
  Mutual Fund Analytics Platform, rather than introducing a second engine
  just for this module.
- `min_score` in `audit_log` is stored as `DOUBLE`, not `DECIMAL` — a
  deliberate choice. MySQL's connector returns `DECIMAL` columns as Python
  `Decimal` objects, which serialize differently in JSON than the plain
  `float` used when a row's hash was first computed, which would silently
  break the hash-chain verification the next time that row was read back.
  `DOUBLE` round-trips as a plain Python `float` on both sides.
- The scoring weights are a simple, explainable starting point — a natural
  "future work" answer is backtesting different weightings against actual
  forward returns.
- The audit trail intentionally logs *only* the request (who asked, what
  filters, what came back) — not full row snapshots of the fund data, since
  that data isn't sensitive/user-owned. If this were logging user PII or
  financial transactions, I'd want the hashes stored somewhere outside the
  same DB file (e.g. written to an external log/service) so a full
  file-level compromise couldn't rewrite the chain *and* its own record of
  itself in one shot.
