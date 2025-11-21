from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Callable, Iterable, List, Sequence, Tuple
import math

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


def diff_k_transform(k: int) -> Transform:
    def _diffk(seq: List[int]) -> List[int]:
        out = list(seq)
        for _ in range(k):
            if len(out) < 2:
                return []
            out = [out[i + 1] - out[i] for i in range(len(out) - 1)]
        return out

    return Transform(name=f"diff^{k}", func=_diffk)


def partial_sum_transform() -> Transform:
    def _psum(seq: List[int]) -> List[int]:
        out: List[int] = []
        s = 0
        for x in seq:
            s += x
            out.append(s)
        return out

    return Transform(name="partial_sum", func=_psum)


def cumulative_product_transform() -> Transform:
    def _cumprod(seq: List[int]) -> List[int]:
        out: List[int] = []
        prod = 1
        for x in seq:
            prod *= x
            out.append(prod)
        return out

    return Transform(name="cumprod", func=_cumprod)


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


def reverse_transform() -> Transform:
    return Transform(name="reverse", func=lambda seq: list(reversed(seq)))


def even_terms_transform() -> Transform:
    return Transform(name="even_terms", func=lambda seq: seq[0::2])


def odd_terms_transform() -> Transform:
    return Transform(name="odd_terms", func=lambda seq: seq[1::2])


def moving_sum_transform(window: int) -> Transform:
    def _mov(seq: List[int]) -> List[int]:
        if window <= 0 or len(seq) < window:
            return []
        return [sum(seq[i : i + window]) for i in range(len(seq) - window + 1)]

    return Transform(name=f"movsum({window})", func=_mov)


def popcount_transform() -> Transform:
    def _pc(seq: List[int]) -> List[int]:
        return [bin(abs(x)).count("1") for x in seq]

    return Transform(name="popcount", func=_pc)


def digit_sum_transform(base: int = 10) -> Transform:
    def _ds(seq: List[int]) -> List[int]:
        out = []
        for x in seq:
            v = abs(x)
            s = 0
            if v == 0:
                out.append(0)
                continue
            while v > 0:
                s += v % base
                v //= base
            out.append(s)
        return out

    return Transform(name=f"digitsum({base})", func=_ds)


def default_transforms(
    scale_values: Iterable[int] = (-2, -1, 2, 3),
    beta_values: Iterable[int] = (),
    shift_values: Iterable[int] = (1, 2),
    allow_diff: bool = True,
    diff_orders: Iterable[int] = (1,),
    allow_partial_sum: bool = True,
    allow_cumprod: bool = False,
    allow_abs: bool = True,
    allow_gcd_norm: bool = True,
    decimate_params: Iterable[Tuple[int, int]] = (),
    allow_reverse: bool = False,
    allow_even_odd: bool = False,
    moving_sum_windows: Iterable[int] = (),
    allow_popcount: bool = False,
    allow_digit_sum: bool = False,
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
        for order in diff_orders:
            if order == 1:
                transforms.append(diff_transform())
            elif order > 1:
                transforms.append(diff_k_transform(order))
    if allow_partial_sum:
        transforms.append(partial_sum_transform())
    if allow_cumprod:
        transforms.append(cumulative_product_transform())
    if allow_abs:
        transforms.append(abs_transform())
    if allow_gcd_norm:
        transforms.append(gcd_normalize_transform())
    for (c, d) in decimate_params:
        transforms.append(decimate_transform(c, d))
    if allow_reverse:
        transforms.append(reverse_transform())
    if allow_even_odd:
        transforms.append(even_terms_transform())
        transforms.append(odd_terms_transform())
    for w in moving_sum_windows:
        transforms.append(moving_sum_transform(w))
    if allow_popcount:
        transforms.append(popcount_transform())
    if allow_digit_sum:
        transforms.append(digit_sum_transform())
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


def describe_chain(chain: Sequence[Transform]) -> tuple[str, str]:
    """
    Return (human_readable, latexish) descriptions for a transform chain.
    """
    human_parts: list[str] = []
    latex_parts: list[str] = []
    for t in chain:
        name = t.name
        if name.startswith("scale("):
            val = name[len("scale(") : -1]
            human_parts.append(f"Multiply by {val}")
            latex_parts.append(f"{val}\\,")
        elif name.startswith("affine("):
            vals = name[len("affine(") : -1]
            k, b = vals.split(",")
            human_parts.append(f"Multiply by {k} then add {b}")
            latex_parts.append(f"{k}\\,x + {b}")
        elif name.startswith("shift("):
            k = name[len("shift(") : -1]
            human_parts.append(f"Drop first {k} term{'s' if k != '1' else ''}")
            latex_parts.append(f"\\mathrm{{shift}}({k})")
        elif name == "diff":
            human_parts.append("First differences")
            latex_parts.append("\\Delta")
        elif name == "partial_sum":
            human_parts.append("Partial sums")
            latex_parts.append("\\mathrm{psum}")
        elif name == "cumprod":
            human_parts.append("Cumulative products")
            latex_parts.append("\\mathrm{cprod}")
        elif name == "abs":
            human_parts.append("Absolute values")
            latex_parts.append("|x|")
        elif name == "gcd_norm":
            human_parts.append("Divide by gcd")
            latex_parts.append("/\\gcd")
        elif name == "reverse":
            human_parts.append("Reverse")
            latex_parts.append("\\mathrm{rev}")
        elif name == "even_terms":
            human_parts.append("Even-index terms")
            latex_parts.append("\\mathrm{even}")
        elif name == "odd_terms":
            human_parts.append("Odd-index terms")
            latex_parts.append("\\mathrm{odd}")
        elif name.startswith("movsum("):
            human_parts.append(f"Moving sum {name[name.index('(')+1:-1]}")
            latex_parts.append("\\mathrm{movsum}")
        elif name == "popcount":
            human_parts.append("Binary popcount")
            latex_parts.append("\\mathrm{popcount}")
        elif name.startswith("digitsum"):
            human_parts.append("Digit sum")
            latex_parts.append("\\mathrm{digitsum}")
        elif name.startswith("decimate("):
            human_parts.append(f"Decimate {name[name.index('(')+1:-1]}")
            latex_parts.append("\\mathrm{decimate}")
        else:
            human_parts.append(name)
            latex_parts.append(name)

    human = ", then ".join(human_parts)
    latex = (" ".join(latex_parts) + "\\,a_n") if latex_parts else ""
    return human, latex
