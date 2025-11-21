from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Callable, Iterable, List, Sequence, Tuple

TransformFunc = Callable[[List[int]], List[int]]


@dataclass(frozen=True)
class Transform:
    name: str
    func: TransformFunc

    def apply(self, seq: List[int]) -> List[int]:
        return self.func(seq)


def make_scale(k: int) -> Transform:
    return Transform(name=f"scale({k})", func=lambda seq: [k * x for x in seq])


def make_affine(k: int, b: int) -> Transform:
    return Transform(name=f"affine({k},{b})", func=lambda seq: [k * x + b for x in seq])


def make_shift(k: int) -> Transform:
    # Shift forward: drop first k elements
    def _shift(seq: List[int]) -> List[int]:
        return seq[k:] if k >= 0 else seq

    sign = f"+{k}" if k >= 0 else str(k)
    return Transform(name=f"shift({sign})", func=_shift)


def diff_transform() -> Transform:
    def _diff(seq: List[int]) -> List[int]:
        return [seq[i + 1] - seq[i] for i in range(len(seq) - 1)]

    return Transform(name="diff", func=_diff)


def partial_sum_transform() -> Transform:
    def _psum(seq: List[int]) -> List[int]:
        out: List[int] = []
        s = 0
        for x in seq:
            s += x
            out.append(s)
        return out

    return Transform(name="partial_sum", func=_psum)


def abs_transform() -> Transform:
    return Transform(name="abs", func=lambda seq: [abs(x) for x in seq])


def gcd_normalize_transform() -> Transform:
    def _gcd_norm(seq: List[int]) -> List[int]:
        import math

        g = 0
        for v in seq:
            g = math.gcd(g, abs(v))
        if g == 0 or g == 1:
            return list(seq)
        return [v // g for v in seq]

    return Transform(name="gcd_norm", func=_gcd_norm)


def decimate_transform(c: int, d: int = 0) -> Transform:
    def _dec(seq: List[int]) -> List[int]:
        if c <= 0:
            return []
        return [seq[c * n + d] for n in range((len(seq) - d + c - 1) // c) if c * n + d < len(seq)]

    return Transform(name=f"decimate({c},{d})", func=_dec)


def default_transforms(
    scale_values: Iterable[int] = (-2, -1, 2, 3),
    beta_values: Iterable[int] = (),
    shift_values: Iterable[int] = (1, 2),
    allow_diff: bool = True,
    allow_partial_sum: bool = True,
    allow_abs: bool = True,
    allow_gcd_norm: bool = True,
    decimate_params: Iterable[Tuple[int, int]] = (),
) -> List[Transform]:
    transforms: List[Transform] = []
    # Affine (k,b) including pure scale
    for k in scale_values:
        if k not in (0, 1):
            transforms.append(make_scale(k))
            for b in beta_values:
                transforms.append(make_affine(k, b))
    for b in beta_values:
        if b != 0:
            transforms.append(make_affine(1, b))
    for k in shift_values:
        transforms.append(make_shift(k))
    if allow_diff:
        transforms.append(diff_transform())
    if allow_partial_sum:
        transforms.append(partial_sum_transform())
    if allow_abs:
        transforms.append(abs_transform())
    if allow_gcd_norm:
        transforms.append(gcd_normalize_transform())
    for (c, d) in decimate_params:
        transforms.append(decimate_transform(c, d))
    return transforms


def enumerate_chains(transforms: Sequence[Transform], max_depth: int) -> List[List[Transform]]:
    """
    Return all transform chains up to max_depth (excluding empty chain).
    """
    chains: List[List[Transform]] = []
    for depth in range(1, max_depth + 1):
        for combo in product(transforms, repeat=depth):
            chains.append(list(combo))
    return chains


def apply_chain(seq: List[int], chain: List[Transform]) -> Tuple[List[int], str]:
    out = list(seq)
    for t in chain:
        if len(out) == 0:
            break
        out = t.apply(out)
    desc = " ∘ ".join(t.name for t in chain)
    return out, desc
