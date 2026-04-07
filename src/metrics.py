from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np
import pandas as pd


def sigma_p(x: np.ndarray, V: np.ndarray) -> float:
    return float(np.sqrt(np.maximum(x @ V @ x, 0.0)))


def ctr_vector(x: np.ndarray, V: np.ndarray) -> np.ndarray:
    denom = float(x @ V @ x)
    if denom <= 0:
        return np.full_like(x, np.nan, dtype=float)
    vx = V @ x
    return (x * vx) / denom


def ctb_vector(x: np.ndarray, V: np.ndarray) -> np.ndarray:
    sp = sigma_p(x, V)
    if sp <= 0:
        return np.full_like(x, np.nan, dtype=float)
    sig = np.sqrt(np.clip(np.diag(V), 0.0, None))
    vx = V @ x
    return vx / (sig * sp)


def D_R(x: np.ndarray, V: np.ndarray, b: np.ndarray) -> float:
    ctr = ctr_vector(x, V)
    return float(np.nansum((ctr - b) ** 2))


def D_B(x: np.ndarray, V: np.ndarray) -> float:
    ctb = ctb_vector(x, V)
    m = float(np.nanmean(ctb))
    return float(np.nansum((ctb - m) ** 2))


def turnover(x_prev: np.ndarray, x_new: np.ndarray) -> float:
    return float(0.5 * np.sum(np.abs(x_new - x_prev)))


def max_drawdown(equity_curve: pd.Series) -> float:
    peak = equity_curve.cummax()
    dd = equity_curve / peak - 1.0
    return float(dd.min())


def annualized_return(daily_returns: pd.Series, ann_factor: int = 252) -> float:
    # geometric annualized return
    g = (1.0 + daily_returns).prod()
    years = len(daily_returns) / ann_factor
    if years <= 0:
        return np.nan
    return float(g ** (1.0 / years) - 1.0)


def annualized_vol(daily_returns: pd.Series, ann_factor: int = 252) -> float:
    return float(daily_returns.std(ddof=1) * np.sqrt(ann_factor))


def sharpe_ratio(daily_returns: pd.Series, ann_factor: int = 252) -> float:
    mu = daily_returns.mean()
    sd = daily_returns.std(ddof=1)
    if sd == 0 or np.isnan(sd):
        return np.nan
    return float((mu / sd) * np.sqrt(ann_factor))
