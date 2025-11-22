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
    # Shift forward: drop first k elements; for negative k, drop last |k| elements.
    def _shift(seq: List[int]) -> List[int]:
        if k == 0:
            return list(seq)
        if k > 0:
            return seq[k:]
        # k < 0 → shift backwards by truncating the tail
        trim = -k
        if trim >= len(seq):
            return []
        return seq[: len(seq) - trim]

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


def mod_transform(m: int) -> Transform:
    def _mod(seq: List[int]) -> List[int]:
        if m <= 0:
            return []
        return [x % m for x in seq]

    return Transform(name=f"mod({m})", func=_mod)


def xor_index_transform() -> Transform:
    def _xor(seq: List[int]) -> List[int]:
        return [x ^ i for i, x in enumerate(seq)]

    return Transform(name="xor_index", func=_xor)


def run_length_encode_transform() -> Transform:
    def _rle(seq: List[int]) -> List[int]:
        if not seq:
            return []
        lengths: List[int] = []
        current = seq[0]
        count = 1
        for x in seq[1:]:
            if x == current:
                count += 1
            else:
                lengths.append(count)
                current = x
                count = 1
        lengths.append(count)
        return lengths

    return Transform(name="rle_len", func=_rle)


def run_length_decode_transform() -> Transform:
    """
    Decode sequence as length,value pairs: [l1,v1,l2,v2,...] -> v1 repeated l1 times, etc.
    If input length is odd or lengths are negative, returns empty list.
    """

    def _rld(seq: List[int]) -> List[int]:
        if len(seq) % 2 == 1:
            return []
        out: List[int] = []
        for i in range(0, len(seq), 2):
            l = seq[i]
            v = seq[i + 1]
            if l < 0:
                return []
            out.extend([v] * l)
        return out

    return Transform(name="rle_dec", func=_rld)

def concat_index_value_transform(base: int = 10) -> Transform:
    """
    Concatenate the 1-based index n with a_n in the given base.
    Example (base 10): a=[3,5,12] -> [13,25,312]
    Negative values keep their sign on the concatenated magnitude.
    """

    def _concat(seq: List[int]) -> List[int]:
        out: List[int] = []
        for i, v in enumerate(seq, start=1):
            sign = -1 if v < 0 else 1
            mag = abs(v)
            out.append(sign * int(f"{_to_base(i, base)}{_to_base(mag, base)}", base))
        return out

    return Transform(name=f"concat(n,a_n,base{base})", func=_concat)


def _to_base(num: int, base: int) -> str:
    if num == 0:
        return "0"
    digits = []
    while num > 0:
        digits.append(int(num % base))
        num //= base
    return "".join(str(d) for d in reversed(digits))


def binomial_transform() -> Transform:
    """
    Classic binomial transform: b_n = sum_{k=0..n} C(n, k) * a_k
    """
    def _bt(seq: List[int]) -> List[int]:
        out: List[int] = []
        for n in range(len(seq)):
            s = 0
            for k in range(n + 1):
                # simple iterative comb
                comb = 1
                for i in range(1, k + 1):
                    comb = comb * (n - i + 1) // i
                s += comb * seq[k]
            out.append(s)
        return out

    return Transform(name="binomial", func=_bt)


def euler_transform() -> Transform:
    """
    Euler transform for integer sequences (assuming a(0)=0 or not used). This simple version:
    b_n = sum_{d|n} d * a_d
    Note: limited to n >= 1 and requires len(seq) > n.
    """
    def _et(seq: List[int]) -> List[int]:
        out: List[int] = []
        for n in range(len(seq)):
            if n == 0:
                out.append(seq[0])
                continue
            s = 0
            for d in range(1, n + 1):
                if n % d == 0 and d < len(seq):
                    s += d * seq[d]
            out.append(s)
        return out

    return Transform(name="euler", func=_et)


def mobius_transform() -> Transform:
    """
    Möbius transform (Dirichlet inverse of constant-1 under convolution):
    b_n = sum_{d|n} mu(n/d) * a_d, with 1-based indexing on n.
    For n=0 (index 0), returns a_0 unchanged.
    """

    def _mu(n: int) -> int:
        # simple integer Möbius function
        n_abs = abs(n)
        if n_abs == 1:
            return 1
        p = 0
        d = 2
        while d * d <= n_abs:
            if n_abs % d == 0:
                n_abs //= d
                if n_abs % d == 0:
                    return 0
                p += 1
            d += 1
        if n_abs > 1:
            p += 1
        return -1 if (p % 2) else 1

    def _mob(seq: List[int]) -> List[int]:
        if not seq:
            return []
        out: List[int] = []
        # index i corresponds to n = i+1
        out.append(seq[0])
        for i in range(1, len(seq)):
            n = i + 1
            s = 0
            for d in range(1, n + 1):
                if n % d == 0 and d - 1 < len(seq):
                    s += _mu(n // d) * seq[d - 1]
            out.append(s)
        return out

    return Transform(name="mobius", func=_mob)


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


def log_transform(base: float) -> Transform:
    """
    Integer log with rounding to nearest int. Drops if any term <= 0 or base<=1.
    """

    def _log(seq: List[int]) -> List[int]:
        if base <= 1:
            return []
        out: List[int] = []
        for v in seq:
            if v <= 0:
                return []
            val = math.log(v, base)
            out.append(int(round(val)))
        return out

    label = "loge" if abs(base - math.e) < 1e-9 else f"log{int(base)}" if float(base).is_integer() else f"log{base:g}"
    return Transform(name=label, func=_log)


def exp_transform(base: float, *, max_mag: float = 1e12) -> Transform:
    """
    Exponentiate integers: base^{a_n} rounded to nearest int. Drops if overflow/too large.
    """

    def _exp(seq: List[int]) -> List[int]:
        if base <= 1:
            return []
        out: List[int] = []
        for v in seq:
            try:
                val = base ** v
            except OverflowError:
                return []
            if not math.isfinite(val) or abs(val) > max_mag:
                return []
            out.append(int(round(val)))
        return out

    label = f"exp{int(base)}" if float(base).is_integer() else f"exp{base:g}"
    return Transform(name=label, func=_exp)


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
    digit_sum_bases: Iterable[int] = (),
    modulus_values: Iterable[int] = (),
    allow_xor_index: bool = False,
    allow_rle: bool = False,
    allow_rle_decode: bool = False,
    allow_concat: bool = False,
    allow_log: bool = False,
    log_bases: Iterable[float] = (),
    allow_exp: bool = False,
    exp_bases: Iterable[float] = (),
    allow_mobius: bool = False,
    allow_binomial: bool = False,
    allow_euler: bool = False,
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
        bases = list(digit_sum_bases) or [10]
        for b in bases:
            transforms.append(digit_sum_transform(b))
    for m in modulus_values:
        transforms.append(mod_transform(m))
    if allow_xor_index:
        transforms.append(xor_index_transform())
    if allow_rle:
        transforms.append(run_length_encode_transform())
    if allow_rle_decode:
        transforms.append(run_length_decode_transform())
    if allow_concat:
        transforms.append(concat_index_value_transform())
    if allow_log:
        bases = list(log_bases) or [2.0]
        for b in bases:
            transforms.append(log_transform(float(b)))
    if allow_exp:
        bases = list(exp_bases) or [2.0]
        for b in bases:
            transforms.append(exp_transform(float(b)))
    if allow_mobius:
        transforms.append(mobius_transform())
    if allow_binomial:
        transforms.append(binomial_transform())
    if allow_euler:
        transforms.append(euler_transform())
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
        elif name.startswith("mod("):
            human_parts.append(f"Mod {name[name.index('(')+1:-1]}")
            latex_parts.append("\\bmod")
        elif name == "xor_index":
            human_parts.append("Bitwise XOR with index")
            latex_parts.append("\\mathrm{xor\\_i}")
        elif name.startswith("decimate("):
            human_parts.append(f"Decimate {name[name.index('(')+1:-1]}")
            latex_parts.append("\\mathrm{decimate}")
        elif name == "rle_len":
            human_parts.append("Run-length encode (lengths)")
            latex_parts.append("\\mathrm{rle}")
        elif name == "rle_dec":
            human_parts.append("Run-length decode (len,val pairs)")
            latex_parts.append("\\mathrm{rldec}")
        elif name == "mobius":
            human_parts.append("Möbius transform")
            latex_parts.append("\\mathrm{Mobius}")
        elif name.startswith("concat("):
            human_parts.append("Concatenate n with a_n")
            latex_parts.append("\\mathrm{concat}(n,a_n)")
        elif name.startswith("log"):
            human_parts.append(f"Integer log base {name[3:]}")
            latex_parts.append("\\log")
        elif name.startswith("exp"):
            human_parts.append(f"Exponentiate base {name[3:]}")
            latex_parts.append("\\exp")
        else:
            human_parts.append(name)
            latex_parts.append(name)

    human = ", then ".join(human_parts)
    latex = (" ".join(latex_parts) + "\\,a_n") if latex_parts else ""
    return human, latex
