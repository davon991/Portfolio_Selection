# data/data_contract.md
# Data Contract (Freeze-1)
# Universe: Broad Asset-Class ETFs
# Version: 1.0.0
# Status: FROZEN

## 0. Purpose
Defines the unique data fields, preprocessing rules, alignment rules, and frequency conventions used by the project.

---

## 1. Universe (Default)
Default ETF set (modifiable only via documented change process):
- US Equities:      SPY
- Developed ex-US:  VEA
- Emerging Markets: VWO
- US Treasuries:    IEF
- Long Treasuries:  TLT
- IG Corporates:    LQD
- High Yield:       HYG
- Gold:             GLD
- Broad Commodities: DBC
- US REITs:         VNQ

Notes:
- n = 10 by default.
- Any change to tickers must update run_manifest.json and be recorded as a version change if it affects comparability.

---

## 2. Raw Data Requirements
For each ticker:
- Daily adjusted close price series (adjusted for splits/dividends).
Required raw fields:
- date (YYYY-MM-DD, no time component)
- ticker (string)
- adj_close (float)

Optional raw fields (not required):
- close, open, high, low, volume

---

## 3. Return Construction (Unique)
Daily simple return for asset i:
- ξ_i(τ) := adj_close_i(τ) / adj_close_i(τ-1) - 1

Rules:
- Returns are computed AFTER alignment (Section 4).
- No forward-looking information may be used.

---

## 4. Alignment and Missing Data (Unique)
Alignment rule (DEFAULT): intersection calendar (listwise):
- Keep only dates where ALL tickers have adj_close available.
- Drop dates failing this condition.
Rationale:
- Avoid injecting artificial zero returns caused by forward fill.

Missing handling:
- If a ticker has missing values on many dates, the run must fail with diagnostics warning unless universe is adjusted.
- All missing statistics must be logged in diagnostics.json.

---

## 5. Frequency Conventions
- Data frequency: daily
- Rebalancing frequency: monthly (last trading day of month within the aligned calendar)
- Annualization factors:
  - daily to annual: 252
  - monthly to annual: 12
Any alternative annualization factor must be explicitly recorded in run_manifest.json (not allowed in mainline).

---

## 6. Date Range and Sample Size
Minimum recommended coverage:
- At least 10 years of daily data (preferred for stable covariance estimation).
The run must record:
- start date, end date
- number of aligned trading days
- number of rebalancing dates K

---

## 7. Cost Convention
Transaction cost parameter c:
- Interpreted as one-way proportional fee applied per unit turnover TO(t)
- c values used in experiments must be declared in config and recorded in run_manifest.json.

---

## 8. Data Output Artifacts (Required)
After preprocessing, must write:
- data/processed/returns.parquet (long format): columns = {date, ticker, ret}
- data/processed/assets.json: per ticker metadata (start/end, missing rate, count)
- data/processed/aligned_calendar.csv: list of aligned dates used

---
