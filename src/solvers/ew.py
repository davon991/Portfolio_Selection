import numpy as np


def solve_ew(n: int) -> np.ndarray:
    return np.full(n, 1.0 / n, dtype=float)
