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
    invertible: bool | None = None
    domain: str = "int"
    risk: str = "medium"
    noise: str = "medium"
    complexity: float = 1.0

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


def alternating_sign_transform() -> Transform:
    """Multiply by (-1)^n (0-based indexing)."""

    def _alt(seq: List[int]) -> List[int]:
        return [x if (i % 2 == 0) else -x for i, x in enumerate(seq)]

    return Transform(
        name="alt_sign",
        func=_alt,
        invertible=True,
        domain="int",
        risk="low",
        noise="low",
        complexity=0.5,
    )


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


def run_length_decode_transform(max_len: int = 10000) -> Transform:
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
            if l == 0:
                continue
            if l > max_len or len(out) > max_len:
                return []
            # guard against huge expansion
            remaining = max_len - len(out)
            to_add = min(l, remaining)
            out.extend([v] * to_add)
            if len(out) >= max_len:
                return []
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
        # O(n^2) incremental binomial coefficient update:
        # C(n,0)=1 and C(n,k+1)=C(n,k)*(n-k)/(k+1).
        for n in range(len(seq)):
            s = 0
            comb = 1
            for k in range(n + 1):
                s += comb * seq[k]
                if k != n:
                    comb = comb * (n - k) // (k + 1)
            out.append(s)
        return out

    return Transform(
        name="binomial",
        func=_bt,
        invertible=True,
        domain="int",
        risk="medium",
        noise="low",
        complexity=1.6,
    )


def inverse_binomial_transform() -> Transform:
    """
    Inverse binomial transform:
      b_n = sum_{k=0..n} (-1)^(n-k) * C(n, k) * a_k
    """

    def _ibt(seq: List[int]) -> List[int]:
        out: List[int] = []
        for n in range(len(seq)):
            s = 0
            comb = 1
            for k in range(n + 1):
                sign = -1 if ((n - k) % 2) else 1
                s += sign * comb * seq[k]
                if k != n:
                    comb = comb * (n - k) // (k + 1)
            out.append(s)
        return out

    return Transform(
        name="inv_binomial",
        func=_ibt,
        invertible=True,
        domain="int",
        risk="medium",
        noise="low",
        complexity=1.7,
    )


def euler_transform() -> Transform:
    """
    Euler transform for integer sequences (assuming a(0)=0 or not used). This simple version:
    b_n = sum_{d|n} d * a_d
    Note: limited to n >= 1 and requires len(seq) > n.
    """
    def _et(seq: List[int]) -> List[int]:
        if not seq:
            return []
        L = len(seq)
        out = [0] * L
        out[0] = seq[0]
        # For n>=1: b_n = sum_{d|n} d * a_d.
        # Compute via a divisor-sieve accumulation (O(n log n)).
        for d in range(1, L):
            contrib = d * seq[d]
            if contrib == 0:
                continue
            for n in range(d, L, d):
                out[n] += contrib
        return out

    return Transform(
        name="euler",
        func=_et,
        invertible=True,
        domain="int",
        risk="medium",
        noise="medium",
        complexity=1.7,
    )


def euler_ogf_transform() -> Transform:
    """
    Canonical Euler transform.

    For input a(n) with n>=1, define:
      C(n) = sum_{d|n} d*a(d),
      b(0)=1,
      n*b(n) = sum_{k=1..n} C(k)*b(n-k).
    Returns b(0..N-1) for input length N.
    """

    def _eogf(seq: List[int]) -> List[int]:
        if not seq:
            return []
        L = len(seq)
        c = [0] * L
        for d in range(1, L):
            contrib = d * seq[d]
            if contrib == 0:
                continue
            for n in range(d, L, d):
                c[n] += contrib

        out = [0] * L
        out[0] = 1
        for n in range(1, L):
            s = 0
            for k in range(1, n + 1):
                s += c[k] * out[n - k]
            if s % n != 0:
                return []
            out[n] = s // n
        return out

    return Transform(
        name="euler_ogf",
        func=_eogf,
        invertible=True,
        domain="int",
        risk="high",
        noise="medium",
        complexity=2.2,
    )


def inverse_euler_ogf_transform() -> Transform:
    """
    Inverse canonical Euler transform.

    Requires b(0)=1. Reconstructs C(n) via:
      C(n) = n*b(n) - sum_{k=1..n-1} C(k)*b(n-k),
    then recovers a(n) by Möbius inversion:
      a(n) = (1/n) * sum_{d|n} mu(d)*C(n/d).
    """

    def _mu(n: int) -> int:
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

    def _inv(seq: List[int]) -> List[int]:
        if not seq:
            return []
        if seq[0] != 1:
            return []
        L = len(seq)
        c = [0] * L
        for n in range(1, L):
            s = n * seq[n]
            for k in range(1, n):
                s -= c[k] * seq[n - k]
            c[n] = s

        out = [0] * L
        for n in range(1, L):
            num = 0
            for d in range(1, n + 1):
                if n % d == 0:
                    num += _mu(d) * c[n // d]
            if num % n != 0:
                return []
            out[n] = num // n
        return out

    return Transform(
        name="inv_euler_ogf",
        func=_inv,
        invertible=True,
        domain="int_with_b0_eq_1",
        risk="high",
        noise="medium",
        complexity=2.4,
    )


def ogf_inverse_transform(max_terms: int = 256, max_abs: int = 10**12) -> Transform:
    """
    OGF inverse transform: given A(x)=sum a_n x^n, return B(x)=1/A(x) truncated.
    Integer-only path: requires exact divisibility at each coefficient step.
    """

    def _ogf_inv(seq: List[int]) -> List[int]:
        if not seq:
            return []
        work = list(seq[:max_terms])
        if not work:
            return []
        a0 = work[0]
        if a0 == 0:
            return []
        if 1 % a0 != 0:
            return []
        L = len(work)
        out = [0] * L
        out[0] = 1 // a0
        for n in range(1, L):
            s = 0
            for k in range(1, n + 1):
                if k < L:
                    s += work[k] * out[n - k]
            num = -s
            if num % a0 != 0:
                return []
            coeff = num // a0
            if abs(coeff) > max_abs:
                return []
            out[n] = coeff
        return out

    return Transform(
        name="ogf_inv",
        func=_ogf_inv,
        invertible=True,
        domain="int_with_a0_nonzero_and_exact_division",
        risk="high",
        noise="medium",
        complexity=2.5,
    )


def _poly_mul_trunc(p: List[int], q: List[int], degree: int) -> List[int]:
    if not p or not q or degree < 0:
        return []
    out_len = min(len(p) + len(q) - 1, degree + 1)
    out = [0] * out_len
    for i, pi in enumerate(p):
        if pi == 0:
            continue
        max_j = min(len(q) - 1, degree - i)
        if max_j < 0:
            continue
        for j in range(max_j + 1):
            out[i + j] += pi * q[j]
    return out


def series_reversion_transform(max_terms: int = 128, max_abs: int = 10**12) -> Transform:
    """
    Compositional inverse (series reversion): given F(x)=sum a_n x^n, find G(x)
    such that F(G(x)) = x, truncated. Integer-only path with strict guards.
    Requires a0=0 and exact divisibility by a1 at each step.
    """

    def _revert(seq: List[int]) -> List[int]:
        if not seq:
            return []
        work = list(seq[:max_terms])
        L = len(work)
        if L < 2:
            return []
        if work[0] != 0:
            return []
        a1 = work[1]
        if a1 == 0:
            return []
        if 1 % a1 != 0:
            return []

        out = [0] * L
        out[1] = 1 // a1

        # For n>=2: coefficient of x^n in F(G(x)) must be 0.
        # Since G has no constant term, b_n appears linearly only in a1*G.
        for n in range(2, L):
            b = out[:n] + [0]
            known = 0
            if n >= 2:
                power = b[:]  # G^1
                for k in range(2, n + 1):
                    power = _poly_mul_trunc(power, b, n)
                    if k >= L:
                        break
                    ak = work[k]
                    if ak == 0:
                        continue
                    coeff_kn = power[n] if n < len(power) else 0
                    known += ak * coeff_kn
            num = -known
            if num % a1 != 0:
                return []
            coeff = num // a1
            if abs(coeff) > max_abs:
                return []
            out[n] = coeff
        return out

    return Transform(
        name="series_reversion",
        func=_revert,
        invertible=True,
        domain="int_with_a0_eq_0_and_exact_division_by_a1",
        risk="high",
        noise="medium",
        complexity=2.7,
    )


def _stirling2_table(n_max: int) -> list[list[int]]:
    s2 = [[0] * (n_max + 1) for _ in range(n_max + 1)]
    s2[0][0] = 1
    for n in range(1, n_max + 1):
        for k in range(1, n + 1):
            s2[n][k] = s2[n - 1][k - 1] + k * s2[n - 1][k]
    return s2


def _stirling1_signed_table(n_max: int) -> list[list[int]]:
    s1 = [[0] * (n_max + 1) for _ in range(n_max + 1)]
    s1[0][0] = 1
    for n in range(1, n_max + 1):
        for k in range(1, n + 1):
            s1[n][k] = s1[n - 1][k - 1] - (n - 1) * s1[n - 1][k]
    return s1


def stirling2_transform() -> Transform:
    """b(n)=sum_{k=0..n} S(n,k)*a(k), where S are Stirling numbers of 2nd kind."""

    def _s2t(seq: List[int]) -> List[int]:
        if not seq:
            return []
        n_max = len(seq) - 1
        s2 = _stirling2_table(n_max)
        out = [0] * len(seq)
        for n in range(len(seq)):
            out[n] = sum(s2[n][k] * seq[k] for k in range(n + 1))
        return out

    return Transform(
        name="stirling2",
        func=_s2t,
        invertible=True,
        domain="int",
        risk="medium",
        noise="low",
        complexity=1.9,
    )


def inverse_stirling2_transform() -> Transform:
    """Inverse of `stirling2` using signed Stirling numbers of first kind."""

    def _inv_s2(seq: List[int]) -> List[int]:
        if not seq:
            return []
        n_max = len(seq) - 1
        s1 = _stirling1_signed_table(n_max)
        out = [0] * len(seq)
        for n in range(len(seq)):
            out[n] = sum(s1[n][k] * seq[k] for k in range(n + 1))
        return out

    return Transform(
        name="inv_stirling2",
        func=_inv_s2,
        invertible=True,
        domain="int",
        risk="medium",
        noise="low",
        complexity=2.0,
    )


def stirling1_transform() -> Transform:
    """b(n)=sum_{k=0..n} s(n,k)*a(k), signed Stirling numbers of first kind."""

    def _s1t(seq: List[int]) -> List[int]:
        if not seq:
            return []
        n_max = len(seq) - 1
        s1 = _stirling1_signed_table(n_max)
        out = [0] * len(seq)
        for n in range(len(seq)):
            out[n] = sum(s1[n][k] * seq[k] for k in range(n + 1))
        return out

    return Transform(
        name="stirling1",
        func=_s1t,
        invertible=True,
        domain="int",
        risk="medium",
        noise="low",
        complexity=1.9,
    )


def inverse_stirling1_transform() -> Transform:
    """Inverse of `stirling1` using Stirling numbers of second kind."""

    def _inv_s1(seq: List[int]) -> List[int]:
        if not seq:
            return []
        n_max = len(seq) - 1
        s2 = _stirling2_table(n_max)
        out = [0] * len(seq)
        for n in range(len(seq)):
            out[n] = sum(s2[n][k] * seq[k] for k in range(n + 1))
        return out

    return Transform(
        name="inv_stirling1",
        func=_inv_s1,
        invertible=True,
        domain="int",
        risk="medium",
        noise="low",
        complexity=2.0,
    )


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


def _factor_abs(n: int) -> dict[int, int]:
    """Return prime factorization of |n| as {p: exponent}. Returns {} for |n| in {0,1}."""
    m = abs(n)
    factors: dict[int, int] = {}
    if m <= 1:
        return factors
    d = 2
    while d * d <= m:
        while m % d == 0:
            factors[d] = factors.get(d, 0) + 1
            m //= d
        d += 1 if d == 2 else 2  # skip even numbers after 2
    if m > 1:
        factors[m] = factors.get(m, 0) + 1
    return factors


def omega_transform() -> Transform:
    """Distinct prime factor count omega(n). Returns empty if any term is 0."""

    def _omega(seq: List[int]) -> List[int]:
        out: List[int] = []
        for v in seq:
            if v == 0:
                return []
            factors = _factor_abs(v)
            out.append(len(factors))
        return out

    return Transform(name="omega", func=_omega)


def big_omega_transform() -> Transform:
    """Total prime factor count with multiplicity Omega(n). Returns empty if any term is 0."""

    def _big(seq: List[int]) -> List[int]:
        out: List[int] = []
        for v in seq:
            if v == 0:
                return []
            factors = _factor_abs(v)
            out.append(sum(factors.values()))
        return out

    return Transform(name="bigomega", func=_big)


def tau_transform() -> Transform:
    """Divisor-count function tau(n). Uses |n|; drops if any term is 0."""

    def _tau(seq: List[int]) -> List[int]:
        out: List[int] = []
        for v in seq:
            if v == 0:
                return []
            factors = _factor_abs(v)
            if not factors:
                out.append(1)
            else:
                d = 1
                for e in factors.values():
                    d *= e + 1
                out.append(d)
        return out

    return Transform(name="tau", func=_tau)


def sigma_transform() -> Transform:
    """Sum-of-divisors function sigma(n). Uses |n|; drops if any term is 0."""

    def _sigma(seq: List[int]) -> List[int]:
        out: List[int] = []
        for v in seq:
            if v == 0:
                return []
            factors = _factor_abs(v)
            if not factors:
                out.append(1)
            else:
                s = 1
                for p, e in factors.items():
                    s *= (p ** (e + 1) - 1) // (p - 1)
                out.append(s)
        return out

    return Transform(name="sigma", func=_sigma)


def phi_transform() -> Transform:
    """Euler totient phi(n). Uses |n|; drops if any term is 0."""

    def _phi(seq: List[int]) -> List[int]:
        out: List[int] = []
        for v in seq:
            if v == 0:
                return []
            m = abs(v)
            if m == 1:
                out.append(1)
                continue
            factors = _factor_abs(m)
            phi_val = m
            for p in factors.keys():
                phi_val = phi_val // p * (p - 1)
            out.append(phi_val)
        return out

    return Transform(name="phi", func=_phi)


def vp_transform(p: int) -> Transform:
    """p-adic valuation v_p(n): exponent of p in |n|. Drops if p<=1 or term is 0."""

    def _vp(seq: List[int]) -> List[int]:
        if p <= 1:
            return []
        out: List[int] = []
        for v in seq:
            if v == 0:
                return []
            m = abs(v)
            e = 0
            while m % p == 0:
                m //= p
                e += 1
            out.append(e)
        return out

    return Transform(
        name=f"vp({p})",
        func=_vp,
        invertible=False,
        domain="int_nonzero",
        risk="low",
        noise="medium",
        complexity=1.3,
    )


def least_prime_factor_transform() -> Transform:
    """Least prime factor of |n|; lpf(1)=1, drops on 0."""

    def _lpf(seq: List[int]) -> List[int]:
        out: List[int] = []
        for v in seq:
            if v == 0:
                return []
            m = abs(v)
            if m == 1:
                out.append(1)
                continue
            f = _factor_abs(m)
            out.append(min(f.keys()) if f else 1)
        return out

    return Transform(
        name="lpf",
        func=_lpf,
        invertible=False,
        domain="int_nonzero",
        risk="low",
        noise="medium",
        complexity=1.3,
    )


def greatest_prime_factor_transform() -> Transform:
    """Greatest prime factor of |n|; gpf(1)=1, drops on 0."""

    def _gpf(seq: List[int]) -> List[int]:
        out: List[int] = []
        for v in seq:
            if v == 0:
                return []
            m = abs(v)
            if m == 1:
                out.append(1)
                continue
            f = _factor_abs(m)
            out.append(max(f.keys()) if f else 1)
        return out

    return Transform(
        name="gpf",
        func=_gpf,
        invertible=False,
        domain="int_nonzero",
        risk="low",
        noise="medium",
        complexity=1.3,
    )


def radical_transform() -> Transform:
    """rad(n): product of distinct prime factors of |n|; rad(1)=1, drops on 0."""

    def _rad(seq: List[int]) -> List[int]:
        out: List[int] = []
        for v in seq:
            if v == 0:
                return []
            m = abs(v)
            if m == 1:
                out.append(1)
                continue
            f = _factor_abs(m)
            r = 1
            for p_ in f.keys():
                r *= p_
            out.append(r)
        return out

    return Transform(
        name="rad",
        func=_rad,
        invertible=False,
        domain="int_nonzero",
        risk="low",
        noise="medium",
        complexity=1.3,
    )


def squarefree_indicator_transform() -> Transform:
    """mu^2(n): 1 iff |n| is squarefree (and n!=0), else 0. Drops on 0."""

    def _sqfree(seq: List[int]) -> List[int]:
        out: List[int] = []
        for v in seq:
            if v == 0:
                return []
            m = abs(v)
            if m == 1:
                out.append(1)
                continue
            f = _factor_abs(m)
            out.append(1 if all(e == 1 for e in f.values()) else 0)
        return out

    return Transform(
        name="squarefree",
        func=_sqfree,
        invertible=False,
        domain="int_nonzero",
        risk="low",
        noise="high",
        complexity=1.1,
    )


def liouville_transform() -> Transform:
    """Liouville lambda(n)=(-1)^Omega(|n|); lambda(1)=1, drops on 0."""

    def _liouville(seq: List[int]) -> List[int]:
        out: List[int] = []
        for v in seq:
            if v == 0:
                return []
            m = abs(v)
            if m == 1:
                out.append(1)
                continue
            f = _factor_abs(m)
            omega = sum(f.values())
            out.append(-1 if (omega % 2) else 1)
        return out

    return Transform(
        name="liouville",
        func=_liouville,
        invertible=False,
        domain="int_nonzero",
        risk="low",
        noise="high",
        complexity=1.3,
    )


def v2_transform() -> Transform:
    """2-adic valuation v_2(n): exponent of 2 in |n|. Drops if any term is 0."""

    def _v2(seq: List[int]) -> List[int]:
        out: List[int] = []
        for v in seq:
            if v == 0:
                return []
            m = abs(v)
            e = 0
            while m % 2 == 0:
                m //= 2
                e += 1
            out.append(e)
        return out

    return Transform(name="v2", func=_v2)


def square_index_transform() -> Transform:
    """Subsequence at square indices: b_n = a_{n^2} (0-based)."""

    def _sq(seq: List[int]) -> List[int]:
        out: List[int] = []
        n = 0
        L = len(seq)
        while n * n < L:
            out.append(seq[n * n])
            n += 1
        return out

    return Transform(name="index_square", func=_sq)


def prime_index_transform() -> Transform:
    """Subsequence at prime indices: b_n = a_{p_n-1} where p_n is n-th prime (2,3,5,...)"""

    def _is_prime(k: int, primes: List[int]) -> bool:
        if k < 2:
            return False
        for p in primes:
            if p * p > k:
                break
            if k % p == 0:
                return False
        return True

    def _prime_index(seq: List[int]) -> List[int]:
        L = len(seq)
        if L < 2:
            return []
        primes: List[int] = []
        out: List[int] = []
        n = 2
        while True:
            if _is_prime(n, primes):
                primes.append(n)
                idx = n - 1
                if idx >= L:
                    break
                out.append(seq[idx])
            n += 1
        return out

    return Transform(name="prime_index", func=_prime_index)


def pow2_index_transform() -> Transform:
    """Subsequence at power-of-two indices: b_n = a_{2^n} (0-based)."""

    def _pow2(seq: List[int]) -> List[int]:
        out: List[int] = []
        L = len(seq)
        idx = 1  # 2^0 = 1
        while idx < L:
            out.append(seq[idx])
            idx <<= 1
        return out

    return Transform(name="index_pow2", func=_pow2)


def factorial_index_transform() -> Transform:
    """Subsequence at factorial indices: b_n = a_{n!} for n>=1 (0-based)."""

    def _fact(seq: List[int]) -> List[int]:
        out: List[int] = []
        L = len(seq)
        fact = 1
        n = 1
        while fact < L:
            out.append(seq[fact])
            n += 1
            fact *= n
        return out

    return Transform(name="index_factorial", func=_fact)


def triangular_index_transform() -> Transform:
    """Subsequence at triangular indices T_n=n(n+1)/2 (0-based)."""

    def _tri(seq: List[int]) -> List[int]:
        out: List[int] = []
        n = 0
        L = len(seq)
        while True:
            idx = n * (n + 1) // 2
            if idx >= L:
                break
            out.append(seq[idx])
            n += 1
        return out

    return Transform(
        name="index_triangular",
        func=_tri,
        invertible=False,
        domain="int",
        risk="low",
        noise="low",
        complexity=1.1,
    )


def fibonacci_index_transform() -> Transform:
    """
    Subsequence at monotone Fibonacci-style indices 0,1,2,3,5,8,...
    (uses the duplicate-free convention to avoid repeated index 1).
    """

    def _fib(seq: List[int]) -> List[int]:
        L = len(seq)
        if L == 0:
            return []
        out: List[int] = [seq[0]]
        a, b = 1, 2
        while a < L:
            out.append(seq[a])
            a, b = b, a + b
        return out

    return Transform(
        name="index_fibonacci",
        func=_fib,
        invertible=False,
        domain="int",
        risk="low",
        noise="low",
        complexity=1.1,
    )


def power_index_transform(power: int) -> Transform:
    """Subsequence at k-th-power indices n^k (0-based), for k>=2."""

    def _powk(seq: List[int]) -> List[int]:
        if power < 2:
            return []
        out: List[int] = []
        L = len(seq)
        n = 0
        while True:
            idx = n**power
            if idx >= L:
                break
            out.append(seq[idx])
            n += 1
        return out

    return Transform(
        name=f"index_powk({power})",
        func=_powk,
        invertible=False,
        domain="int",
        risk="low",
        noise="low",
        complexity=1.2,
    )


def ratio_int_transform() -> Transform:
    """
    Integer quotient transform: b_n = a_{n+1} / a_n.
    Drops if any denominator is zero or division is non-integral.
    """

    def _ratio(seq: List[int]) -> List[int]:
        if len(seq) < 2:
            return []
        out: List[int] = []
        for a, b in zip(seq, seq[1:]):
            if a == 0:
                return []
            if b % a != 0:
                return []
            out.append(b // a)
        return out

    return Transform(
        name="ratio_int",
        func=_ratio,
        invertible=False,
        domain="int_nonzero_adjacent_with_exact_division",
        risk="medium",
        noise="medium",
        complexity=1.2,
    )


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
    allow_alt_sign: bool = False,
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
    allow_inverse_binomial: bool = False,
    allow_euler: bool = False,
    allow_euler_ogf: bool = False,
    allow_inverse_euler_ogf: bool = False,
    allow_stirling1: bool = False,
    allow_stirling2: bool = False,
    allow_inverse_stirling1: bool = False,
    allow_inverse_stirling2: bool = False,
    allow_ogf_inverse: bool = False,
    allow_series_reversion: bool = False,
    allow_omega: bool = False,
    allow_bigomega: bool = False,
    allow_tau: bool = False,
    allow_sigma: bool = False,
    allow_phi: bool = False,
    allow_v2: bool = False,
    allow_index_square: bool = False,
    allow_prime_index: bool = False,
    allow_index_pow2: bool = False,
    allow_index_factorial: bool = False,
    allow_index_triangular: bool = False,
    allow_index_fibonacci: bool = False,
    index_power_values: Iterable[int] = (),
    vp_values: Iterable[int] = (),
    allow_lpf: bool = False,
    allow_gpf: bool = False,
    allow_rad: bool = False,
    allow_squarefree: bool = False,
    allow_liouville: bool = False,
    allow_ratio_int: bool = False,
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
    if allow_alt_sign:
        transforms.append(alternating_sign_transform())
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
    if allow_inverse_binomial:
        transforms.append(inverse_binomial_transform())
    if allow_euler:
        transforms.append(euler_transform())
    if allow_euler_ogf:
        transforms.append(euler_ogf_transform())
    if allow_inverse_euler_ogf:
        transforms.append(inverse_euler_ogf_transform())
    if allow_stirling1:
        transforms.append(stirling1_transform())
    if allow_stirling2:
        transforms.append(stirling2_transform())
    if allow_inverse_stirling1:
        transforms.append(inverse_stirling1_transform())
    if allow_inverse_stirling2:
        transforms.append(inverse_stirling2_transform())
    if allow_ogf_inverse:
        transforms.append(ogf_inverse_transform())
    if allow_series_reversion:
        transforms.append(series_reversion_transform())
    if allow_omega:
        transforms.append(omega_transform())
    if allow_bigomega:
        transforms.append(big_omega_transform())
    if allow_tau:
        transforms.append(tau_transform())
    if allow_sigma:
        transforms.append(sigma_transform())
    if allow_phi:
        transforms.append(phi_transform())
    if allow_v2:
        transforms.append(v2_transform())
    for p in vp_values:
        transforms.append(vp_transform(int(p)))
    if allow_lpf:
        transforms.append(least_prime_factor_transform())
    if allow_gpf:
        transforms.append(greatest_prime_factor_transform())
    if allow_rad:
        transforms.append(radical_transform())
    if allow_squarefree:
        transforms.append(squarefree_indicator_transform())
    if allow_liouville:
        transforms.append(liouville_transform())
    if allow_index_square:
        transforms.append(square_index_transform())
    if allow_prime_index:
        transforms.append(prime_index_transform())
    if allow_index_pow2:
        transforms.append(pow2_index_transform())
    if allow_index_factorial:
        transforms.append(factorial_index_transform())
    if allow_index_triangular:
        transforms.append(triangular_index_transform())
    if allow_index_fibonacci:
        transforms.append(fibonacci_index_transform())
    for k in index_power_values:
        transforms.append(power_index_transform(int(k)))
    if allow_ratio_int:
        transforms.append(ratio_int_transform())
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
        elif name == "alt_sign":
            human_parts.append("Multiply by (-1)^n")
            latex_parts.append("(-1)^n")
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
        elif name == "binomial":
            human_parts.append("Binomial transform")
            latex_parts.append("\\mathrm{Binomial}")
        elif name == "inv_binomial":
            human_parts.append("Inverse binomial transform")
            latex_parts.append("\\mathrm{InvBinomial}")
        elif name == "euler":
            human_parts.append("Euler transform")
            latex_parts.append("\\mathrm{Euler}")
        elif name == "euler_ogf":
            human_parts.append("Canonical Euler transform (OGF product)")
            latex_parts.append("\\mathrm{EulerOGF}")
        elif name == "inv_euler_ogf":
            human_parts.append("Inverse canonical Euler transform")
            latex_parts.append("\\mathrm{InvEulerOGF}")
        elif name == "stirling1":
            human_parts.append("Stirling transform (1st kind)")
            latex_parts.append("\\mathrm{Stirling1}")
        elif name == "stirling2":
            human_parts.append("Stirling transform (2nd kind)")
            latex_parts.append("\\mathrm{Stirling2}")
        elif name == "inv_stirling1":
            human_parts.append("Inverse Stirling transform (1st kind)")
            latex_parts.append("\\mathrm{InvStirling1}")
        elif name == "inv_stirling2":
            human_parts.append("Inverse Stirling transform (2nd kind)")
            latex_parts.append("\\mathrm{InvStirling2}")
        elif name == "ogf_inv":
            human_parts.append("OGF inverse transform (1/A(x))")
            latex_parts.append("\\mathrm{OGFInv}")
        elif name == "series_reversion":
            human_parts.append("Compositional inverse (series reversion)")
            latex_parts.append("\\mathrm{SeriesRev}")
        elif name in ("omega", "bigomega", "tau", "sigma", "phi", "v2"):
            human_parts.append(name)
            latex_parts.append(f"\\mathrm{{{name}}}")
        elif name.startswith("vp("):
            human_parts.append(f"p-adic valuation {name[name.index('(')+1:-1]}")
            latex_parts.append("\\mathrm{v_p}")
        elif name in ("lpf", "gpf", "rad", "squarefree", "liouville", "ratio_int"):
            human_parts.append(name)
            latex_parts.append(f"\\mathrm{{{name}}}")
        elif name in ("index_square", "prime_index", "index_pow2", "index_factorial", "index_triangular", "index_fibonacci"):
            human_parts.append(name)
            latex_parts.append(f"\\mathrm{{{name}}}")
        elif name.startswith("index_powk("):
            human_parts.append(name)
            latex_parts.append("\\mathrm{index\\_powk}")
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
