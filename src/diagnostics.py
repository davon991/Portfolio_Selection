from __future__ import annotations

from typing import Any, Dict, List
import numpy as np
import pandas as pd


def build_diagnostics(cfg: Dict[str, Any], returns: pd.DataFrame, rebal_dates: List[pd.Timestamp], all_out: Dict[str, Any], delta: float, eps_db: float) -> Dict[str, Any]:
    tickers = list(returns.columns)
    warnings: List[str] = []

    # Data checks (post-alignment returns)
    missing_rate_by_asset = {t: float(returns[t].isna().mean()) for t in tickers}
    missing_rate_by_date = float(returns.isna().any(axis=1).mean())

    lookahead_check_passed = True  # enforced by slicing logic in backtest
    if missing_rate_by_date > 0:
        warnings.append("Returns wide matrix contains missing values after alignment; check data_prep alignment.")
        lookahead_check_passed = False

    # Solver / strategy checks (focus on proposed)
    prop = all_out.get("RB_CTB_BAND", {})
    drdb = prop.get("drdb", pd.DataFrame())
    conv_rate = float(prop.get("convergence_rate", np.nan))
    failed_dates = prop.get("failures", [])
    avg_iter = float(prop.get("avg_iterations", np.nan))

    # Constraint checks
    if len(drdb):
        active_rate = float(drdb["active"].mean())
        db_margin = drdb["db"] - drdb["delta"]
        db_margin_stats = {
            "mean": float(db_margin.mean()),
            "p05": float(db_margin.quantile(0.05)),
            "p50": float(db_margin.quantile(0.50)),
            "p95": float(db_margin.quantile(0.95)),
        }
    else:
        active_rate = np.nan
        db_margin_stats = {}

    # Boundary rates (0 or x_max) using proposed weights
    w = prop.get("weights", pd.DataFrame())
    x_max = float(cfg["experiment"]["x_max"])
    tol = 1e-12
    boundary_zero_rate = float((w.drop(columns=["date"]).values <= tol).mean()) if len(w) else np.nan
    boundary_xmax_rate = float((np.abs(w.drop(columns=["date"]).values - x_max) <= 1e-8).mean()) if len(w) else np.nan

    # Turnover checks
    avg_turnover = float(drdb["turnover"].mean()) if len(drdb) else np.nan
    turnover_p95 = float(drdb["turnover"].quantile(0.95)) if len(drdb) else np.nan
    turnover_outlier_dates = drdb.loc[drdb["turnover"] >= turnover_p95, "date"].astype(str).tolist() if len(drdb) else []

    # Protocol-like warnings (do not enforce rejection here; protocol enforces in calibration)
    if not np.isnan(active_rate) and (active_rate < 0.05 or active_rate > 0.90):
        warnings.append(f"Constraint active_rate={active_rate:.3f} is extreme; check delta calibration or feasibility.")
    if not np.isnan(boundary_xmax_rate) and boundary_xmax_rate > 0.30:
        warnings.append(f"Cap-binding too often: boundary_xmax_rate={boundary_xmax_rate:.3f}.")
    if not np.isnan(boundary_zero_rate) and boundary_zero_rate > 0.80:
        warnings.append(f"Excess sparsity: boundary_zero_rate={boundary_zero_rate:.3f}.")
    if not np.isnan(conv_rate) and conv_rate < 0.99:
        warnings.append(f"Solver convergence_rate={conv_rate:.3f} below 0.99.")

    return {
        "data_checks": {
            "missing_rate_by_asset": missing_rate_by_asset,
            "missing_rate_by_date_any": missing_rate_by_date,
            "alignment_rule_used": "intersection_calendar",
            "lookahead_check_passed": lookahead_check_passed,
            "notes": "V_t estimated using returns[t-L:t) only; weights applied from t inclusive to next rebalance date (per spec).",
        },
        "solver_checks": {
            "convergence_rate": conv_rate,
            "failed_dates": failed_dates,
            "avg_iterations": avg_iter,
        },
        "constraint_checks": {
            "active_rate": active_rate,
            "db_margin_stats": db_margin_stats,
            "boundary_rate_zero": boundary_zero_rate,
            "boundary_rate_xmax": boundary_xmax_rate,
        },
        "turnover_checks": {
            "avg_turnover": avg_turnover,
            "turnover_p95": turnover_p95,
            "turnover_outlier_dates": turnover_outlier_dates[:20],
        },
        "warnings": warnings,
    }
