"""Exact, bounded searches for polynomial formulas by index residue."""

from collections.abc import Callable, Sequence
from itertools import pairwise
from math import comb
from typing import Any, cast

MAX_PERIOD = 8
MAX_DEGREE = 3
MIN_HOLDOUT = 2


class _Cancelled(Exception):
    pass


def _fit(terms: Sequence[int], indices: range, check: Callable[[], None]) -> list[int] | None:
    for size in range(1, min(MAX_DEGREE + 1, len(indices) - MIN_HOLDOUT) + 1):
        check()
        differences = [terms[i] for i in indices[:size]]
        coefficients = []
        while differences:
            coefficients.append(differences[0])
            differences = [b - a for a, b in pairwise(differences)]
        for m, i in enumerate(indices[size:], start=size):
            if m % 256 == 0:
                check()
            if terms[i] != sum(c * comb(m, k) for k, c in enumerate(coefficients)):
                break
        else:
            return coefficients
    return None


def _formula(coefficients: list[int]) -> str:
    c0, c1, c2, c3 = coefficients + [0] * (MAX_DEGREE + 1 - len(coefficients))
    # Expand binom(m, k) into ordinary powers; scale by 3! to stay integral.
    scaled = [6 * c0, 6 * c1 - 3 * c2 + 2 * c3, 3 * (c2 - c3), c3]
    if all(c % 6 == 0 for c in scaled):
        terms = [(c // 6, basis) for c, basis in zip(scaled, ("", "m", "m^2", "m^3"))][::-1]
    else:
        terms = list(zip(coefficients, ("", "m", "binom(m, 2)", "binom(m, 3)")))
    pieces = []
    for coefficient, basis in terms:
        if not coefficient:
            continue
        magnitude = abs(coefficient)
        term = str(magnitude)
        if basis:
            term = basis if magnitude == 1 else f"{magnitude}*{basis}"
        sign = "-" if coefficient < 0 else "+"
        sign = f" {sign} " if pieces else sign if coefficient < 0 else ""
        pieces.append(sign + term)
    return "".join(pieces) or "0"


def detect_quasipolynomial(
    seq: Sequence[int | None], *, index_origin: int = 0, should_stop: Callable[[], bool] | None = None
) -> dict[str, Any] | None:
    """Return the smallest supported period, or None for no match or a wildcard query.

    In each residue class, fit the lowest supported degree using its first d+1
    terms, then check all remaining terms, with at least two held out. Exact
    coefficients multiply binom(m, k), where m = (n - first_index) / period.
    These checks establish agreement with the supplied data, not extrapolation.
    Return None if should_stop requests cancellation before the fit completes.
    """
    def check() -> None:
        if should_stop is not None and should_stop():
            raise _Cancelled

    try:
        for i, term in enumerate(seq):
            if term is None:
                return None
            if i % 256 == 0:
                check()
        return _detect(cast(Sequence[int], seq), index_origin, check)
    except _Cancelled:
        return None


def _detect(terms: Sequence[int], index_origin: int, check: Callable[[], None]) -> dict[str, Any] | None:
    for period in range(1, min(MAX_PERIOD, len(terms) // (1 + MIN_HOLDOUT)) + 1):
        constituents = []
        branches = []
        for residue in range(period):
            offset = (residue - index_origin) % period
            first = index_origin + offset
            indices = range(offset, len(terms), period)
            coefficients = _fit(terms, indices, check)
            if coefficients is None:
                break
            formula = _formula(coefficients)
            constituents.append({
                "residue": residue,
                "first_index": first,
                "degree": len(coefficients) - 1,
                "coefficients": coefficients,
                "formula": formula,
                "fit_terms": len(coefficients),
                "holdout_terms": len(indices) - len(coefficients),
            })
            index = "m" if period == 1 else f"{period}m"
            if first:
                index += f" {'+' if first > 0 else '-'} {abs(first)}"
            branches.append(f"a({index}) = {formula}")
        else:
            check()
            fit_terms = sum(c["fit_terms"] for c in constituents)
            return {
                "period": period,
                "index_origin": index_origin,
                "formula": "; ".join(branches),
                "constituents": constituents,
                "validation": {
                    "fit_terms": fit_terms,
                    "holdout_terms": len(terms) - fit_terms,
                    "min_holdout_terms_per_class": min(c["holdout_terms"] for c in constituents),
                },
            }
    return None
