# paper/spec.md
# Project Spec (Freeze-0)
# Title: CtR Primary Objective + CtB Risk-Control Constraint (Band)
# Version: 1.0.0
# Status: FROZEN (Any change requires spec_diff.md + smoke run)

## 0. Scope
This spec fixes the unique notation, metric definitions, optimization model, backtest accounting, and required outputs.
All subsequent writing, code, and results must conform exactly to this document.

---

## 1. Notation (Unique)
- Assets: i = 1,...,n
- Rebalancing dates: t ∈ 𝒯 = {t_1,...,t_K} (monthly by default)
- Daily simple returns vector: ξ(τ) = (ξ_1(τ),...,ξ_n(τ))ᵀ for trading day τ
- Weight vector at rebalancing date t: x(t) ∈ ℝⁿ
- Feasible set (long-only with cap):
  𝒲 := { x ∈ ℝⁿ : 1ᵀx = 1, 0 ≤ x_i ≤ x_max }
- Rolling risk window length (daily observations): L (fixed per run)
- Covariance (risk input) at rebalancing date t:
  V_t := Cov_t(ξ) estimated from daily returns {ξ(τ)} over τ = t-L,...,t-1
- Asset volatilities: σ_i := sqrt( (V_t)_{ii} )
- Portfolio volatility:
  σ_p(x) := sqrt( xᵀ V_t x )

---

## 2. Metric System (Unique)

### 2.1 CtR (Contribution to Risk)
For any feasible x:
- CtR_i(x) := [ x_i (V_t x)_i ] / [ xᵀ V_t x ]
- Additivity: ∑_{i=1}^n CtR_i(x) = 1

Risk budget vector:
- b = (b_1,...,b_n)ᵀ, b_i > 0, ∑ b_i = 1
- ERC baseline uses b_i = 1/n

CtR deviation (primary objective component):
- D_R(x; b) := ∑_{i=1}^n ( CtR_i(x) - b_i )^2

### 2.2 CtB (Correlation to Basket)
Define CtB_i as correlation between asset return and portfolio return under (V_t, x):
- CtB_i(x) := Corr( ξ_i, ξ_p ) where ξ_p = xᵀ ξ
Using covariance identity:
- CtB_i(x) := (V_t x)_i / [ σ_i σ_p(x) ]

Cross-sectional mean:
- meanCtB(x) := (1/n) ∑_{i=1}^n CtB_i(x)

CtB dispersion (risk-control metric):
- D_B(x) := ∑_{i=1}^n ( CtB_i(x) - meanCtB(x) )^2

### 2.3 Turnover and Costs
Single-period turnover at rebalancing date t:
- TO(t) := (1/2) ∑_{i=1}^n | x_i(t) - x_i(t_prev) |

Proportional transaction cost model (applied at rebalancing):
- net_return(τ) = gross_return(τ) - c * TO(t) for τ ∈ [t, next_rebalancing)
where c is fixed “one-way fee rate” per unit turnover.

---

## 3. Strategies (Baselines + Proposed)

### 3.1 EW (Equal Weight)
x_i(t) = 1/n

### 3.2 GMV (Global Minimum Variance under 𝒲)
At each t:
- x_GMV(t) ∈ argmin_{x ∈ 𝒲} xᵀ V_t x

### 3.3 ERC (CtR-only baseline under 𝒲)
At each t:
- x_ERC(t) ∈ argmin_{x ∈ 𝒲} D_R(x; 1/n * 1)

### 3.4 Proposed: RB–CtB Band (CtR primary + CtB constraint)
At each t:
Constrained form (conceptual):
- minimize   D_R(x; b) + η ||x - x(t_prev)||_2^2 + γ ||x||_2^2
  subject to x ∈ 𝒲,  D_B(x) ≤ δ

Implementation form (band via hinge penalty; mainline solver):
Let (u)_+ := max(u, 0). Define objective:
- J(x) := D_R(x; b) + η ||x - x_prev||_2^2 + γ ||x||_2^2 + (ρ/2) * ( D_B(x) - δ )_+^2
Solve:
- x*(t) ∈ argmin_{x ∈ 𝒲} J(x)

Parameters:
- δ: CtB dispersion threshold (from calibration_protocol.md)
- η: smoothing parameter (from calibration_protocol.md)
- γ: L2 stabilizer (from calibration_protocol.md)
- ρ: penalty strength (fixed by config; must be recorded in run_manifest.json)

Constraint-active flag (for reporting):
- active(t) := 1{ D_B(x(t)) ≥ δ - eps_db }, eps_db fixed constant in config.

---

## 4. Backtest Accounting (Unique)
- Daily returns are computed from adjusted close prices (see data_contract.md).
- Risk input V_t uses only past data up to t-1 (no look-ahead).
- Weights x(t) are applied to subsequent daily returns until next rebalancing date.
- Gross portfolio daily return:
  r_p_gross(τ) := x(t)ᵀ ξ(τ) for τ in holding period after t
- Net portfolio daily return:
  r_p_net(τ) := r_p_gross(τ) - c * TO(t) for τ in holding period after t

Performance metrics:
- Annualization must follow frequency conventions stated in data_contract.md (daily to annual, monthly to annual).

---

## 5. Required Outputs (Contract)
Each run writes to results/<run_id>/ and MUST include:

### 5.1 Traceability
- config.json
- run_manifest.json (schema fixed below)
- diagnostics.json (schema fixed below)
- analysis_pack.json (schema fixed below)

### 5.2 Machine-readable core
- panel.parquet (long panel; required)
- summary_metrics.csv (required)
- dr_db.csv (required)
- perf_daily.csv (required)
- weights.csv (wide; required)
- weights_long.csv (long; required)
- ctr_long.csv (required)
- ctb_long.csv (required)

### 5.3 Figures (pdf+png)
- fig_equity_curve
- fig_drawdown
- fig_ctr_bar (selected windows; data references must be in panel)
- fig_ctb_bar (selected windows)
- fig_db_vs_delta_timeseries
- fig_pareto_dr_db (optional but recommended)

---

## 6. run_manifest.json (Schema)
Required keys:
- run_id
- created_utc
- spec_version (this spec version)
- data_contract_version
- calibration_protocol_version
- code_commit (git hash or "NA" if not using git)
- python_version
- platform
- universe (list of tickers)
- date_range: {start, end}
- frequency: {data:"daily", rebalance:"monthly"}
- window_L
- covariance_method (e.g., "ledoit_wolf_shrinkage")
- constraints: {x_max}
- costs: {c}
- parameters: {delta, eta, gamma, rho, eps_db}
- outputs: list of file paths written

---

## 7. diagnostics.json (Schema)
Must include:
- data_checks:
  - missing_rate_by_asset
  - missing_rate_by_date
  - alignment_rule_used
  - lookahead_check_passed (bool) + notes
- solver_checks:
  - convergence_rate
  - failed_dates (list)
  - avg_iterations (if available)
- constraint_checks:
  - active_rate
  - db_margin_stats (db - delta summary)
  - boundary_rate_zero
  - boundary_rate_xmax
- turnover_checks:
  - avg_turnover
  - turnover_p95
  - turnover_outlier_dates
- warnings (list of strings)

---

## 8. analysis_pack.json (Schema)
Must include summary statistics used for writing Chapter 6 and defense:
- run_id
- headline_metrics:
  - for each strategy: ann_return, ann_vol, sharpe, max_drawdown, avg_turnover, net_sharpe
- mechanism_metrics:
  - db_reduction_vs_erc (relative/absolute)
  - dr_change_vs_erc
  - active_rate
  - typical_active_periods (optional)
- robustness_flags:
  - any_warning (bool)
  - key_warnings (list)
- pointers:
  - table_files (list)
  - figure_files (list)

---
