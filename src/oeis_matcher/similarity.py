from __future__ import annotations

import math
from typing import List, Tuple


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def correlation(x: List[int], y: List[int]) -> float:
    """
    Pearson correlation on first min(len(x), len(y)) terms.
    Returns 0 if less than 2 points or zero variance.
    """
    n = min(len(x), len(y))
    if n < 2:
        return 0.0
    x = x[:n]
    y = y[:n]
    mx = _mean(x)
    my = _mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    denx = math.sqrt(sum((a - mx) ** 2 for a in x))
    deny = math.sqrt(sum((b - my) ** 2 for b in y))
    if denx == 0 or deny == 0:
        return 0.0
    return num / (denx * deny)


def mse_after_scale_offset(query: List[int], target: List[int]) -> Tuple[float, float, float]:
    """
    Compute best-fitting scale a and offset b minimizing MSE between a*target + b and query
    over the first n terms (n = min lengths). Returns (mse, a, b).
    """
    n = min(len(query), len(target))
    if n == 0:
        return float("inf"), 0.0, 0.0
    x = target[:n]
    y = query[:n]
    # solve least squares for a, b: minimize ||a x_i + b - y_i||
    sumx = sum(x)
    sumy = sum(y)
    sumxx = sum(v * v for v in x)
    sumxy = sum(a * b for a, b in zip(x, y))
    denom = n * sumxx - sumx * sumx
    if denom == 0:
        a = 0.0
        b = _mean(y)
    else:
        a = (n * sumxy - sumx * sumy) / denom
        b = (sumy - a * sumx) / n
    mse = _mean([(a * xi + b - yi) ** 2 for xi, yi in zip(x, y)])
    return mse, a, b


def growth_rate(values: List[int]) -> float:
    """
    Rough growth rate estimate: average of log(|a_n|+1)/(n+1) over available terms.
    Returns 0 if no terms or all zeros.
    """
    acc = 0.0
    count = 0
    for idx, v in enumerate(values):
        mag = abs(v)
        if mag == 0:
            continue
        acc += math.log(mag + 1.0) / (idx + 1)
        count += 1
    if count == 0:
        return 0.0
    return acc / count
