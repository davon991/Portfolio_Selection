from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Any, Dict, List

from src.covariance import estimate_covariance
from src.metrics import (
    ctr_vector,
    ctb_vector,
    D_R,
    D_B,
    turnover,
    annualized_return,
    annualized_vol,
    sharpe_ratio,
    max_drawdown,
)
from src.solvers.ew import solve_ew
from src.solvers.gmv import solve_gmv
from src.solvers.erc import solve_erc
from src.solvers.rb_ctb_band import solve_rb_ctb_band
from src.utils import save_json


def _load_returns_long(path: str) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _returns_wide(returns_long: pd.DataFrame, tickers: List[str]) -> pd.DataFrame:
    wide = returns_long.pivot(index="date", columns="ticker", values="ret").sort_index()
    wide = wide[tickers]
    wide = wide.dropna(how="any")
    return wide


def _monthly_last_rebalance_dates(dates: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """
    Per data_contract.md: monthly rebalancing on the last trading day of each month
    within the aligned calendar.

    Pandas >= 2.2 uses 'ME' for month-end frequency (deprecated 'M').
    """
    if len(dates) == 0:
        return pd.DatetimeIndex([])

    s = pd.Series(np.ones(len(dates)), index=dates)
    # group by month-end and take the last index in each group
    # Use 'ME' (month-end) rather than deprecated 'M'
    grouped = s.resample("ME")
    last_dates = grouped.apply(lambda x: x.index[-1]).dropna()

    return pd.DatetimeIndex(last_dates.values).sort_values()


def _split_rebal_dates(rebal: List[pd.Timestamp], train_frac: float, val_frac: float) -> Dict[str, List[pd.Timestamp]]:
    K = len(rebal)
    n_train = int(np.floor(K * train_frac))
    n_val = int(np.floor(K * val_frac))
    train = rebal[:n_train]
    val = rebal[n_train:n_train + n_val]
    test = rebal[n_train + n_val:]
    return {"train": train, "val": val, "test": test}


def _holding_slice(dates: pd.DatetimeIndex, t: pd.Timestamp, t_next: pd.Timestamp | None) -> pd.DatetimeIndex:
    if t_next is None:
        return dates[dates >= t]
    return dates[(dates >= t) & (dates < t_next)]


def _compute_daily_portfolio_returns(returns: pd.DataFrame, weights: pd.Series, hold_dates: pd.DatetimeIndex) -> pd.Series:
    sub = returns.loc[hold_dates, :]
    rp = sub.values @ weights.values
    return pd.Series(rp, index=hold_dates)


def _write_csv(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False)


def _annual_metrics(daily: pd.Series, ann_factor: int = 252) -> Dict[str, float]:
    eq = (1.0 + daily).cumprod()
    return {
        "ann_return": annualized_return(daily, ann_factor=ann_factor),
        "ann_vol": annualized_vol(daily, ann_factor=ann_factor),
        "sharpe": sharpe_ratio(daily, ann_factor=ann_factor),
        "max_drawdown": max_drawdown(eq),
    }


def _run_strategy_over_rebal(
    name: str,
    returns: pd.DataFrame,
    rebal_dates: List[pd.Timestamp],
    V_method: str,
    L: int,
    x_max: float,
    cost_c: float,
    b: np.ndarray,
    delta: float | None,
    eta: float | None,
    gamma: float | None,
    rho: float | None,
    eps_db: float,
    solver_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    dates = returns.index
    tickers = list(returns.columns)
    n = len(tickers)

    weights_records = []
    ctr_records = []
    ctb_records = []
    drdb_records = []
    perf_records = []

    x_prev = np.full(n, 1.0 / n)

    failures: List[str] = []
    iters: List[int] = []

    for k, t in enumerate(rebal_dates):
        pos_arr = dates.get_indexer([t])
        if pos_arr.size == 0 or pos_arr[0] == -1:
            continue
        pos = int(pos_arr[0])

        # ensure enough history for covariance estimation
        if pos < L:
            continue

        window = returns.iloc[pos - L:pos, :].values
        V = estimate_covariance(window, V_method)

        # choose solver
        if name == "EW":
            x = solve_ew(n)
            success, msg, nit = True, "EW", 0
        elif name == "GMV":
            res = solve_gmv(V, x_max=x_max, x0=x_prev, max_iter=solver_cfg["max_iter"], tol=solver_cfg["tol"])
            x, success, msg, nit = res.x, res.success, res.message, res.nit
        elif name == "ERC":
            res = solve_erc(V, x_max=x_max, b=b, x0=x_prev, max_iter=solver_cfg["max_iter"], tol=solver_cfg["tol"])
            x, success, msg, nit = res.x, res.success, res.message, res.nit
        elif name == "RB_CTB_BAND":
            assert delta is not None and eta is not None and gamma is not None and rho is not None
            res = solve_rb_ctb_band(
                V=V,
                x_prev=x_prev,
                x_max=x_max,
                b=b,
                delta=delta,
                eta=eta,
                gamma=gamma,
                rho=rho,
                x0=x_prev,
                max_iter=solver_cfg["max_iter"],
                tol=solver_cfg["tol"],
            )
            x, success, msg, nit = res.x, res.success, res.message, res.nit
        else:
            raise ValueError("Unknown strategy name")

        if not success:
            failures.append(str(pd.to_datetime(t).date()))
        iters.append(int(nit))

        to = turnover(x_prev, x)
        ctr = ctr_vector(x, V)
        ctb = ctb_vector(x, V)
        dr = D_R(x, V, b)
        db = D_B(x, V)
        active = int(db >= (delta - eps_db)) if (name == "RB_CTB_BAND" and delta is not None) else 0

        # holding period
        t_next = rebal_dates[k + 1] if (k + 1) < len(rebal_dates) else None
        hold_dates = _holding_slice(dates, t, t_next)

        gross = _compute_daily_portfolio_returns(returns, pd.Series(x, index=tickers), hold_dates)
        # Per spec.md: net_return(τ) = gross_return(τ) - c*TO(t) for τ in holding period after t
        net = gross - cost_c * to

        for d in hold_dates:
            perf_records.append({"date": d, "strategy": name, "gross": float(gross.loc[d]), "net": float(net.loc[d])})

        weights_records.append({"date": t, **{tickers[i]: float(x[i]) for i in range(n)}})
        ctr_records.append({"date": t, **{tickers[i]: float(ctr[i]) for i in range(n)}})
        ctb_records.append({"date": t, **{tickers[i]: float(ctb[i]) for i in range(n)}})
        drdb_records.append({
            "date": t,
            "dr": float(dr),
            "db": float(db),
            "delta": float(delta) if delta is not None else np.nan,
            "active": int(active),
            "turnover": float(to),
            "nit": int(nit),
        })

        x_prev = x.copy()

    out = {
        "weights": pd.DataFrame(weights_records),
        "ctr": pd.DataFrame(ctr_records),
        "ctb": pd.DataFrame(ctb_records),
        "drdb": pd.DataFrame(drdb_records),
        "perf": pd.DataFrame(perf_records),
        "failures": failures,
        "avg_iterations": float(np.mean(iters)) if iters else np.nan,
        "convergence_rate": float(1.0 - (len(failures) / max(len(rebal_dates), 1))),
    }
    return out


def _panel_long_from_outputs(
    strategy_name: str,
    weights_df: pd.DataFrame,
    ctr_df: pd.DataFrame,
    ctb_df: pd.DataFrame,
    drdb_df: pd.DataFrame,
) -> pd.DataFrame:
    w_long = weights_df.melt(id_vars=["date"], var_name="asset", value_name="weight")
    c_long = ctr_df.melt(id_vars=["date"], var_name="asset", value_name="ctr")
    b_long = ctb_df.melt(id_vars=["date"], var_name="asset", value_name="ctb")

    panel = w_long.merge(c_long, on=["date", "asset"], how="left").merge(b_long, on=["date", "asset"], how="left")
    panel["strategy"] = strategy_name
    panel = panel.merge(drdb_df[["date", "dr", "db", "delta", "active", "turnover"]], on="date", how="left")
    return panel


def run_full_pipeline(cfg: Dict[str, Any], run_dir: Path, data_artifacts: Dict[str, str]) -> Dict[str, Any]:
    tickers = [t.upper() for t in cfg["data"]["tickers"]]
    returns_long = _load_returns_long(data_artifacts["returns_parquet"])
    returns = _returns_wide(returns_long, tickers)
    dates = returns.index

    if cfg["experiment"]["rebalance"] != "monthly_last":
        raise ValueError("Only monthly_last is supported per data_contract.md")

    rebal_dates = _monthly_last_rebalance_dates(dates).to_list()
    cal = cfg["calibration"]
    split = _split_rebal_dates(rebal_dates, cal["train_frac"], cal["val_frac"])

    L = int(cfg["experiment"]["window_L"])
    V_method = cfg["experiment"]["covariance_method"]
    x_max = float(cfg["experiment"]["x_max"])
    cost_c = float(cfg["experiment"]["cost_c"])
    eps_db = float(cfg["experiment"]["eps_db"])
    rho = float(cfg["solver"]["rho"])

    n = len(tickers)
    b = np.full(n, 1.0 / n)  # ERC budget default
    solver_cfg = {"max_iter": int(cfg["solver"]["max_iter"]), "tol": float(cfg["solver"]["tol"])}

    # --- Calibration: gamma ---
    s_list = []
    for t in split["train"]:
        pos = dates.get_indexer([t])[0]
        if pos < L:
            continue
        window = returns.iloc[pos - L:pos, :].values
        V = estimate_covariance(window, V_method)
        s_list.append(float(np.trace(V) / n))
    if not s_list:
        raise RuntimeError("Insufficient history for covariance estimation in train set.")
    s_med = float(np.median(s_list))

    alpha_grid = [float(a) for a in cal["alpha_grid"]]
    gamma_candidates = [a * s_med for a in alpha_grid]
    gamma = float(gamma_candidates[0])  # minimal stabilizer (protocol’s selection refined via diagnostics)

    # --- Calibration: delta candidates from ERC DB distribution + feasibility check ---
    z = []
    m_vals = []

    from scipy.optimize import minimize
    from src.metrics import D_B as DB_metric

    def solve_db_min(V: np.ndarray, x0: np.ndarray) -> np.ndarray:
        bounds = [(0.0, x_max) for _ in range(n)]
        cons = [{"type": "eq", "fun": lambda x: np.sum(x) - 1.0}]
        res = minimize(lambda x: DB_metric(x, V), x0=x0, method="SLSQP", bounds=bounds, constraints=cons, options={"maxiter": 1200, "ftol": 1e-10})
        x = res.x
        x = np.clip(x / x.sum(), 0.0, x_max)
        x = x / x.sum()
        return x

    x0 = np.full(n, 1.0 / n)

    for t in split["train"]:
        pos = dates.get_indexer([t])[0]
        if pos < L:
            continue
        V = estimate_covariance(returns.iloc[pos - L:pos, :].values, V_method)

        erc_res = solve_erc(V, x_max=x_max, b=b, x0=x0, max_iter=solver_cfg["max_iter"], tol=solver_cfg["tol"])
        x_erc = erc_res.x
        z.append(D_B(x_erc, V))

        x_bmin = solve_db_min(V, x0=x0)
        m_vals.append(D_B(x_bmin, V))

    z = np.array(z, dtype=float)
    m_vals = np.array(m_vals, dtype=float)
    if len(z) == 0:
        raise RuntimeError("No ERC samples in train for delta calibration.")

    m_lower = float(np.max(m_vals)) if len(m_vals) else 0.0

    p_grid = [float(p) for p in cal["p_grid"]]
    delta_candidates = []
    for p in p_grid:
        d = float(np.quantile(z, p))
        if d >= m_lower:
            delta_candidates.append((p, d))
    if len(delta_candidates) == 0:
        raise RuntimeError("All delta candidates invalid by feasibility lower bound.")

    TO_target = float(cal["TO_target"])
    eps_TO = float(cal["eps_TO"])

    def avg_turnover_for_eta(delta: float, eta: float) -> float:
        out = _run_strategy_over_rebal(
            name="RB_CTB_BAND",
            returns=returns,
            rebal_dates=split["val"],
            V_method=V_method,
            L=L,
            x_max=x_max,
            cost_c=cost_c,
            b=b,
            delta=delta,
            eta=eta,
            gamma=gamma,
            rho=rho,
            eps_db=eps_db,
            solver_cfg=solver_cfg,
        )
        drdb = out["drdb"]
        return float(drdb["turnover"].mean()) if len(drdb) else np.nan

    def calibrate_eta(delta: float) -> float:
        eta_low = 0.0
        eta_high = 1.0
        to_high = avg_turnover_for_eta(delta, eta_high)
        guard = 0
        while (not np.isnan(to_high)) and (to_high > TO_target) and guard < 12:
            eta_high *= 2.0
            to_high = avg_turnover_for_eta(delta, eta_high)
            guard += 1
        if np.isnan(to_high):
            return eta_high

        for _ in range(20):
            eta_mid = 0.5 * (eta_low + eta_high)
            to_mid = avg_turnover_for_eta(delta, eta_mid)
            if np.isnan(to_mid):
                eta_low = eta_mid
                continue
            if to_mid > TO_target:
                eta_low = eta_mid
            else:
                eta_high = eta_mid
            if abs(to_mid - TO_target) <= eps_TO:
                return eta_mid
        return eta_high

    def net_sharpe_for(delta: float, eta: float) -> float:
        out = _run_strategy_over_rebal(
            name="RB_CTB_BAND",
            returns=returns,
            rebal_dates=split["val"],
            V_method=V_method,
            L=L,
            x_max=x_max,
            cost_c=cost_c,
            b=b,
            delta=delta,
            eta=eta,
            gamma=gamma,
            rho=rho,
            eps_db=eps_db,
            solver_cfg=solver_cfg,
        )
        perf = out["perf"]
        if len(perf) == 0:
            return np.nan
        net = perf.groupby("date")["net"].sum().sort_index()
        return sharpe_ratio(net, ann_factor=252)

    candidate_scores = []
    for p, delta in delta_candidates:
        eta = calibrate_eta(delta)
        s = net_sharpe_for(delta, eta)
        candidate_scores.append({"p": p, "delta": delta, "eta": eta, "net_sharpe": float(s)})

    candidate_scores = [c for c in candidate_scores if not np.isnan(c["net_sharpe"])]
    if not candidate_scores:
        raise RuntimeError("No valid candidate produced finite net Sharpe on validation.")

    candidate_scores.sort(key=lambda d: (d["net_sharpe"], d["delta"]), reverse=True)
    chosen = candidate_scores[0]
    delta_star = float(chosen["delta"])
    eta_star = float(chosen["eta"])

    # --- Final backtests ---
    strategies = ["EW", "GMV", "ERC", "RB_CTB_BAND"]
    all_out: Dict[str, Any] = {}
    for sname in strategies:
        if sname == "RB_CTB_BAND":
            out = _run_strategy_over_rebal(
                name=sname,
                returns=returns,
                rebal_dates=rebal_dates,
                V_method=V_method,
                L=L,
                x_max=x_max,
                cost_c=cost_c,
                b=b,
                delta=delta_star,
                eta=eta_star,
                gamma=gamma,
                rho=rho,
                eps_db=eps_db,
                solver_cfg=solver_cfg,
            )
        else:
            out = _run_strategy_over_rebal(
                name=sname,
                returns=returns,
                rebal_dates=rebal_dates,
                V_method=V_method,
                L=L,
                x_max=x_max,
                cost_c=cost_c,
                b=b,
                delta=None,
                eta=None,
                gamma=None,
                rho=None,
                eps_db=eps_db,
                solver_cfg=solver_cfg,
            )
        all_out[sname] = out

    written_files: List[str] = []

    # perf_daily.csv
    perf_all = pd.concat([all_out[s]["perf"] for s in strategies], ignore_index=True)
    perf_daily = perf_all.groupby(["date", "strategy"], as_index=False)[["gross", "net"]].sum().sort_values(["date", "strategy"])
    perf_daily_path = run_dir / "perf_daily.csv"
    _write_csv(perf_daily_path, perf_daily)
    written_files.append(str(perf_daily_path))

    # Proposed required exports
    w_prop = all_out["RB_CTB_BAND"]["weights"].copy()
    w_prop_path = run_dir / "weights.csv"
    _write_csv(w_prop_path, w_prop)
    written_files.append(str(w_prop_path))

    w_long = w_prop.melt(id_vars=["date"], var_name="asset", value_name="weight")
    w_long_path = run_dir / "weights_long.csv"
    _write_csv(w_long_path, w_long)
    written_files.append(str(w_long_path))

    ctr_prop = all_out["RB_CTB_BAND"]["ctr"].copy()
    ctr_long = ctr_prop.melt(id_vars=["date"], var_name="asset", value_name="ctr")
    ctr_path = run_dir / "ctr_long.csv"
    _write_csv(ctr_path, ctr_long)
    written_files.append(str(ctr_path))

    ctb_prop = all_out["RB_CTB_BAND"]["ctb"].copy()
    ctb_long = ctb_prop.melt(id_vars=["date"], var_name="asset", value_name="ctb")
    ctb_path = run_dir / "ctb_long.csv"
    _write_csv(ctb_path, ctb_long)
    written_files.append(str(ctb_path))

    drdb_prop = all_out["RB_CTB_BAND"]["drdb"].copy()
    drdb_path = run_dir / "dr_db.csv"
    _write_csv(drdb_path, drdb_prop)
    written_files.append(str(drdb_path))

    # panel.parquet (all strategies)
    panels = []
    for sname in strategies:
        panels.append(_panel_long_from_outputs(
            strategy_name=sname,
            weights_df=all_out[sname]["weights"],
            ctr_df=all_out[sname]["ctr"],
            ctb_df=all_out[sname]["ctb"],
            drdb_df=all_out[sname]["drdb"],
        ))
    panel = pd.concat(panels, ignore_index=True)
    panel_path = run_dir / "panel.parquet"
    panel.to_parquet(panel_path, index=False)
    written_files.append(str(panel_path))

    # summary_metrics.csv
    summary_rows = []
    for sname in strategies:
        daily = perf_daily[perf_daily["strategy"] == sname].set_index("date").sort_index()
        gross = daily["gross"]
        net = daily["net"]
        m_g = _annual_metrics(gross)
        m_n = _annual_metrics(net)
        avg_to = float(all_out[sname]["drdb"]["turnover"].mean()) if len(all_out[sname]["drdb"]) else np.nan
        summary_rows.append({
            "strategy": sname,
            **{f"gross_{k}": v for k, v in m_g.items()},
            **{f"net_{k}": v for k, v in m_n.items()},
            "avg_turnover": avg_to,
        })
    summary = pd.DataFrame(summary_rows)
    summary_path = run_dir / "summary_metrics.csv"
    _write_csv(summary_path, summary)
    written_files.append(str(summary_path))

    # diagnostics.json and analysis_pack.json
    from src.diagnostics import build_diagnostics
    diagnostics = build_diagnostics(cfg, returns, rebal_dates, all_out, delta_star, eps_db)
    save_json(run_dir / "diagnostics.json", diagnostics)
    written_files.append(str(run_dir / "diagnostics.json"))

    analysis_pack = {
        "run_id": run_dir.name,
        "headline_metrics": {
            row["strategy"]: {
                "ann_return": row["net_ann_return"],
                "ann_vol": row["net_ann_vol"],
                "sharpe": row["net_sharpe"],
                "max_drawdown": row["net_max_drawdown"],
                "avg_turnover": row["avg_turnover"],
            }
            for _, row in summary.iterrows()
        },
        "mechanism_metrics": {
            "db_reduction_vs_erc": float(
                (all_out["ERC"]["drdb"]["db"].mean() - all_out["RB_CTB_BAND"]["drdb"]["db"].mean())
                if len(all_out["ERC"]["drdb"]) and len(all_out["RB_CTB_BAND"]["drdb"]) else np.nan
            ),
            "dr_change_vs_erc": float(
                (all_out["RB_CTB_BAND"]["drdb"]["dr"].mean() - all_out["ERC"]["drdb"]["dr"].mean())
                if len(all_out["ERC"]["drdb"]) and len(all_out["RB_CTB_BAND"]["drdb"]) else np.nan
            ),
            "active_rate": float((all_out["RB_CTB_BAND"]["drdb"]["active"].mean()) if len(all_out["RB_CTB_BAND"]["drdb"]) else np.nan),
        },
        "robustness_flags": {
            "any_warning": bool(len(diagnostics.get("warnings", [])) > 0),
            "key_warnings": diagnostics.get("warnings", []),
        },
        "pointers": {
            "table_files": ["summary_metrics.csv", "dr_db.csv", "perf_daily.csv"],
            "figure_files": [],
        },
    }
    save_json(run_dir / "analysis_pack.json", analysis_pack)
    written_files.append(str(run_dir / "analysis_pack.json"))

    final_parameters = {"delta": delta_star, "eta": eta_star, "gamma": gamma}
    return {"final_parameters": final_parameters, "written_files": written_files}
