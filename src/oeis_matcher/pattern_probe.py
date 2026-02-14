from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class ModClassSlice:
    """
    A subsequence extracted by index congruence.

    Convention: user input term i corresponds to n = n0 + i (0-based i).
    """

    k: int
    r: int
    n0: int
    ns: List[int]
    terms: List[int]


def split_by_mod_class(terms: Sequence[int], k: int, *, n0: int = 1) -> Dict[int, ModClassSlice]:
    """
    Split a term list into k subsequences by n mod k.

    Example (n0=1): terms[0] is a(1), terms[1] is a(2), ...
    """
    if k <= 0:
        raise ValueError("k must be positive")
    if not terms:
        return {r: ModClassSlice(k=k, r=r, n0=n0, ns=[], terms=[]) for r in range(k)}

    buckets: Dict[int, Tuple[List[int], List[int]]] = {r: ([], []) for r in range(k)}
    for i, v in enumerate(terms):
        n = n0 + i
        r = n % k
        ns, vs = buckets[r]
        ns.append(n)
        vs.append(int(v))
    return {r: ModClassSlice(k=k, r=r, n0=n0, ns=ns, terms=vs) for r, (ns, vs) in buckets.items()}


def v_p(n: int, p: int) -> Tuple[int, int]:
    """
    Return (v_p(n), n / p^{v_p(n)}) for p>1.
    Uses |n| for valuations and preserves sign in the residual.
    """
    if p <= 1:
        raise ValueError("p must be > 1")
    if n == 0:
        return 0, 0
    sign = -1 if n < 0 else 1
    m = abs(n)
    v = 0
    while m % p == 0:
        m //= p
        v += 1
    return v, sign * m


@dataclass(frozen=True)
class ValuationRow:
    n: int
    value: int
    v2: int
    v5: int
    rest_2_5: int


def valuations_2_5(terms: Sequence[int], *, n0: int = 1) -> List[ValuationRow]:
    """
    Compute (v2, v5, remaining cofactor) per term.
    """
    rows: List[ValuationRow] = []
    for i, a in enumerate(terms):
        n = n0 + i
        v2, rest2 = v_p(int(a), 2)
        v5, rest25 = v_p(rest2, 5)
        rows.append(ValuationRow(n=n, value=int(a), v2=v2, v5=v5, rest_2_5=rest25))
    return rows


@dataclass(frozen=True)
class MPowNormalization:
    """
    Normalization of terms indexed by n = k*m + r:
      ratio(m) = a(n) / m^(exp_coeff*m).
    """

    k: int
    r: int
    n0: int
    exp_coeff: int
    m_values: List[int]
    ratios: List[Fraction]


def normalize_by_m_pow_cm(
    mod_slice: ModClassSlice,
    *,
    exp_coeff: int = 2,
    require_m_positive: bool = True,
) -> MPowNormalization:
    """
    For a mod class slice with n = k*m + r, compute a(n) / m^(exp_coeff*m).

    This is particularly useful for Hadamard-type determinant sequences where
    m^(2m) shows up for n mod 4 classes.
    """
    if exp_coeff < 0:
        raise ValueError("exp_coeff must be >= 0")
    m_values: List[int] = []
    ratios: List[Fraction] = []
    for n, a in zip(mod_slice.ns, mod_slice.terms):
        m = (n - mod_slice.r) // mod_slice.k
        if require_m_positive and m <= 0:
            continue
        denom = pow(m, exp_coeff * m)
        if denom == 0:
            continue
        m_values.append(int(m))
        ratios.append(Fraction(int(a), int(denom)))
    return MPowNormalization(
        k=mod_slice.k,
        r=mod_slice.r,
        n0=mod_slice.n0,
        exp_coeff=exp_coeff,
        m_values=m_values,
        ratios=ratios,
    )


def all_integers(values: Iterable[Fraction]) -> bool:
    return all(v.denominator == 1 for v in values)


def try_fit_affine(xs: Sequence[int], ys: Sequence[int]) -> Optional[Tuple[Fraction, Fraction]]:
    """
    If ys is exactly affine in xs (y = a*x + b), return (a,b) as Fractions.
    Otherwise return None.
    """
    if len(xs) != len(ys):
        raise ValueError("xs and ys length mismatch")
    if len(xs) < 2:
        return None
    x0, y0 = xs[0], ys[0]
    x1, y1 = xs[1], ys[1]
    if x1 == x0:
        return None
    a = Fraction(y1 - y0, x1 - x0)
    b = Fraction(y0) - a * Fraction(x0)
    for x, y in zip(xs, ys):
        if Fraction(y) != a * Fraction(x) + b:
            return None
    return a, b

