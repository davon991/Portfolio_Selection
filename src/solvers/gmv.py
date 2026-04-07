from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
from scipy.optimize import minimize


@dataclass
class SolverResult:
    x: np.ndarray
    success: bool
    message: str
    nit: int


def solve_gmv(V: np.ndarray, x_max: float, x0: Optional[np.ndarray] = None, max_iter: int = 1000, tol: float = 1e-9) -> SolverResult:
    n = V.shape[0]
    if x0 is None:
        x0 = np.full(n, 1.0 / n)

    bounds = [(0.0, x_max) for _ in range(n)]
    cons = [{"type": "eq", "fun": lambda x: np.sum(x) - 1.0}]

    def obj(x: np.ndarray) -> float:
        return float(x @ V @ x)

    res = minimize(obj, x0=x0, method="SLSQP", bounds=bounds, constraints=cons, options={"maxiter": max_iter, "ftol": tol})

    x = res.x.copy()
    # Enforce exact budget by renormalization (small numerical drift)
    s = x.sum()
    if s != 0:
        x = x / s
        x = np.clip(x, 0.0, x_max)
        x = x / x.sum()

    return SolverResult(x=x, success=bool(res.success), message=str(res.message), nit=int(res.nit))
