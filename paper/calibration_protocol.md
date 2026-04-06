# paper/calibration_protocol.md
# Calibration Protocol (Freeze-2)
# Version: 1.0.0
# Status: FROZEN

## 0. Purpose
Defines a rule-based, auditable calibration of δ, η, γ for the RB–CtB Band strategy.
Calibration must be strictly chronological and low-degree-of-freedom.

---

## 1. Data Split (Unique)
Let rebalancing dates be 𝒯 = {t_1,...,t_K}. Split chronologically:
- Train: first 60% of rebalancing dates
- Validation: next 20%
- Test: last 20%

All calibration choices (δ, η, γ) are finalized using Train/Validation ONLY.
Test is held out and must not influence calibration.

---

## 2. δ (CtB Threshold) Calibration

### 2.1 Construct ERC baseline distribution
For each t in Train:
1) Estimate V_t from past L daily returns.
2) Solve ERC baseline:
   x_ERC(t) ∈ argmin_{x ∈ 𝒲} D_R(x; 1/n * 1)
3) Compute z(t) := D_B( x_ERC(t) )

Collect {z(t)} over Train.

### 2.2 Candidate threshold family
Fix candidate quantile grid (LOW DoF):
- 𝒫 := {0.4, 0.5, 0.6, 0.7, 0.8}

Define:
- δ(p) := Quantile_p( {z(t)} ), p ∈ 𝒫

### 2.3 Select p* on Validation
For each p in 𝒫:
- Fix δ = δ(p)
- Temporarily fix γ (Section 4) and calibrate η (Section 3) using Validation.
- Run Validation backtest for RB–CtB Band and record:
  - net Sharpe (primary)
  - max drawdown (secondary)
  - average turnover (constraint)
Select p* by:
- Maximize net Sharpe subject to average turnover ≤ TO_target (fixed below)
If multiple p tie within tolerance, choose the largest δ (less restrictive) among tied candidates.

### 2.4 Feasibility safeguard (required)
Compute (on Train ∪ Validation) a feasibility lower bound:
- For each t, solve x_Bmin(t) ∈ argmin_{x ∈ 𝒲} D_B(x)
- Record m(t) := D_B(x_Bmin(t))
Require:
- δ(p) ≥ max_t m(t)  (otherwise δ(p) is invalid and removed from candidate set)

---

## 3. η (Smoothing) Calibration
η is calibrated to satisfy a trading stability requirement, not to maximize performance directly.

### 3.1 Fixed turnover target
Set:
- TO_target := 0.15  (monthly average turnover target; fixed constant)
- tolerance ε_TO := 0.01

### 3.2 Monotone search
Given fixed δ and γ, determine η on Validation by bisection:
- Find η* such that | avg_turnover_val(η*) - TO_target | ≤ ε_TO
Search interval:
- η_low = 0
- η_high = η_init_high (increase until avg_turnover_val(η_high) < TO_target)

Record η* in run_manifest.json.

---

## 4. γ (L2 Stabilizer) Calibration
γ follows a scale rule with minimal sensitivity.

### 4.1 Scale rule candidates
Let s_t := tr(V_t)/n at each t. Define:
- γ(α) := α * median_{t∈Train}( s_t )
Candidate set:
- α ∈ {1e-6, 1e-5, 1e-4}

### 4.2 Selection rule
Choose the smallest α such that:
- Solver convergence rate ≥ 99% on Validation
- No persistent boundary pathology (Section 5)
If α=1e-6 already satisfies, fix it and treat γ as “minimal stabilizer.”

---

## 5. Rejection Criteria (Hard Checks)
A calibrated (δ, η, γ) is rejected if ANY holds on Validation:

### 5.1 Constraint activation extremes
Let active_rate be fraction of rebalancing dates where D_B(x(t)) ≥ δ - eps_db.
Reject if:
- active_rate < 0.05  OR  active_rate > 0.90

### 5.2 Boundary pathology
Let boundary_zero_rate = average fraction of assets with x_i(t) = 0.
Let boundary_xmax_rate = average fraction of assets with x_i(t) = x_max.
Reject if:
- boundary_xmax_rate > 0.30  (cap-binding too often)
- boundary_zero_rate > 0.80  (excess sparsity; indicates over-constraint or estimation issues)

### 5.3 Turnover pathology
Reject if:
- avg_turnover_val > TO_target + 2*ε_TO
- turnover_p95 is extremely high relative to median (must be logged; threshold set in code as a multiple, e.g., p95/median > 5)

### 5.4 Solver failures
Reject if:
- convergence_rate < 0.99
- any repeated failure streak (≥3 consecutive rebalancing dates fail)

All rejection reasons must be written to diagnostics.json.

---

## 6. Finalization
After selecting p*, η*, γ:
- Freeze parameters and rerun full Test evaluation without changing any calibration decisions.
- Record:
  - δ, η, γ, ρ, eps_db
  - p* and candidate set results
in run_manifest.json and analysis_pack.json.

---
