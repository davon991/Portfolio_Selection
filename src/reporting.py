from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import matplotlib.pyplot as plt
import pandas as pd


def _save_fig(path: Path, formats: List[str]) -> None:
    for fmt in formats:
        plt.savefig(path.with_suffix(f".{fmt}"), bbox_inches="tight", dpi=200)


def make_all_figures(cfg: Dict[str, Any], run_dir: Path) -> None:
    fmts = cfg.get("reporting", {}).get("figure_format", ["png"])
    perf = pd.read_csv(run_dir / "perf_daily.csv")
    perf["date"] = pd.to_datetime(perf["date"])
    perf = perf.sort_values(["date", "strategy"])

    # Equity curve (net)
    plt.figure()
    for s in perf["strategy"].unique():
        s_df = perf[perf["strategy"] == s].groupby("date", as_index=False)["net"].sum().sort_values("date")
        eq = (1.0 + s_df["net"]).cumprod()
        plt.plot(s_df["date"], eq, label=s)
    plt.legend()
    plt.title("Equity Curve (Net)")
    _save_fig(run_dir / "fig_equity_curve", fmts)
    plt.close()

    # Drawdown (net) for proposed only
    plt.figure()
    s = "RB_CTB_BAND"
    s_df = perf[perf["strategy"] == s].groupby("date", as_index=False)["net"].sum().sort_values("date")
    eq = (1.0 + s_df["net"]).cumprod()
    peak = eq.cummax()
    dd = eq / peak - 1.0
    plt.plot(s_df["date"], dd)
    plt.title("Drawdown (Net) - RB_CTB_BAND")
    _save_fig(run_dir / "fig_drawdown", fmts)
    plt.close()

    # DB vs delta timeseries (rebalance-level)
    drdb = pd.read_csv(run_dir / "dr_db.csv")
    drdb["date"] = pd.to_datetime(drdb["date"])
    plt.figure()
    plt.plot(drdb["date"], drdb["db"], label="D_B")
    plt.plot(drdb["date"], drdb["delta"], label="delta")
    plt.legend()
    plt.title("D_B vs delta (Rebalance-level)")
    _save_fig(run_dir / "fig_db_vs_delta_timeseries", fmts)
    plt.close()

    # CtR/CtB bar charts for selected windows (last N rebalance dates)
    N = int(cfg.get("reporting", {}).get("selected_windows", 3))
    # Use long files
    ctr = pd.read_csv(run_dir / "ctr_long.csv")
    ctb = pd.read_csv(run_dir / "ctb_long.csv")
    ctr["date"] = pd.to_datetime(ctr["date"])
    ctb["date"] = pd.to_datetime(ctb["date"])
    selected_dates = sorted(ctr["date"].unique())[-N:]

    # CtR bars
    plt.figure(figsize=(10, 4))
    sub = ctr[ctr["date"].isin(selected_dates)]
    # average across selected dates for compactness
    agg = sub.groupby("asset", as_index=False)["ctr"].mean().sort_values("ctr", ascending=False)
    plt.bar(agg["asset"], agg["ctr"])
    plt.xticks(rotation=45, ha="right")
    plt.title(f"CtR (avg over last {N} rebalances) - RB_CTB_BAND")
    _save_fig(run_dir / "fig_ctr_bar", fmts)
    plt.close()

    # CtB bars
    plt.figure(figsize=(10, 4))
    sub = ctb[ctb["date"].isin(selected_dates)]
    agg = sub.groupby("asset", as_index=False)["ctb"].mean().sort_values("ctb", ascending=False)
    plt.bar(agg["asset"], agg["ctb"])
    plt.xticks(rotation=45, ha="right")
    plt.title(f"CtB (avg over last {N} rebalances) - RB_CTB_BAND")
    _save_fig(run_dir / "fig_ctb_bar", fmts)
    plt.close()
