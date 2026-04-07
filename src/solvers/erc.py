from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy.optimize import minimize

from src.metrics import D_R


@dataclass
class SolverResult:
    x: np.ndarray
    success: bool
    message: str
    nit: int


def solve_erc(V: np.ndarray, x_max: float, b: np.ndarray, x0: Optional[np.ndarray] = None, max_iter: int = 1500, tol: float = 1e-10) -> SolverResult:
    n = V.shape[0]
    if x0 is None:
        x0 = np.full(n, 1.0 / n)

    bounds = [(0.0, x_max) for _ in range(n)]
    cons = [{"type": "eq", "fun": lambda x: np.sum(x) - 1.0}]

    def obj(x: np.ndarray) -> float:
        return D_R(x, V, b)

    res = minimize(obj, x0=x0, method="SLSQP", bounds=bounds, constraints=cons, options={"maxiter": max_iter, "ftol": tol})

    x = res.x.copy()
    s = x.sum()
    if s != 0:
        x = np.clip(x / s, 0.0, x_max)
        x = x / x.sum()

    return SolverResult(x=x, success=bool(res.success), message=str(res.message), nit=int(res.nit))
