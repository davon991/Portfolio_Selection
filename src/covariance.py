from __future__ import annotations

from typing import Literal
import numpy as np
from sklearn.covariance import LedoitWolf


def estimate_covariance(returns_window: np.ndarray, method: str) -> np.ndarray:
    """
    returns_window: shape (L, n), rows are time, columns are assets
    method:
      - "sample"
      - "ledoit_wolf_shrinkage"
    """
    if returns_window.ndim != 2:
        raise ValueError("returns_window must be 2D (L,n)")
    if method == "sample":
        return np.cov(returns_window, rowvar=False, ddof=1)
    if method == "ledoit_wolf_shrinkage":
        lw = LedoitWolf().fit(returns_window)
        return lw.covariance_
    raise ValueError("Unknown covariance_method")
