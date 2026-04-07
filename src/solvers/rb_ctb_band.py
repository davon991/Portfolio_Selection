from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy.optimize import minimize

from src.metrics import D_R, D_B


@dataclass
class SolverResult:
    x: np.ndarray
    success: bool
    message: str
    nit: int
    db: float
    dr: float


def solve_rb_ctb_band(
    V: np.ndarray,
    x_prev: np.ndarray,
    x_max: float,
    b: np.ndarray,
    delta: float,
    eta: float,
    gamma: float,
    rho: float,
    x0: Optional[np.ndarray] = None,
    max_iter: int = 1500,
    tol: float = 1e-10,
) -> SolverResult:
    n = V.shape[0]
    if x0 is None:
        x0 = x_prev.copy()

    bounds = [(0.0, x_max) for _ in range(n)]
    cons = [{"type": "eq", "fun": lambda x: np.sum(x) - 1.0}]

    def obj(x: np.ndarray) -> float:
        dr = D_R(x, V, b)
        db = D_B(x, V)
        hinge = max(db - delta, 0.0)
        return float(dr + eta * np.sum((x - x_prev) ** 2) + gamma * np.sum(x ** 2) + 0.5 * rho * hinge * hinge)

    res = minimize(obj, x0=x0, method="SLSQP", bounds=bounds, constraints=cons, options={"maxiter": max_iter, "ftol": tol})

    x = res.x.copy()
    s = x.sum()
    if s != 0:
        x = np.clip(x / s, 0.0, x_max)
        x = x / x.sum()

    dr = D_R(x, V, b)
    db = D_B(x, V)
    return SolverResult(x=x, success=bool(res.success), message=str(res.message), nit=int(res.nit), db=db, dr=dr)
