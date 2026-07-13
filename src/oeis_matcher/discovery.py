from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Callable

from .matcher import match_exact_db
from .models import SequenceQuery


@dataclass(frozen=True)
class DiscoveryResult:
    ids: list[str]
    provenance: dict[str, list[str]]
    diagnostics: dict[str, object]


def _fits_linear_recurrence(coeffs: list[int], terms: list[int]) -> bool:
    """
    coeffs encode c0*a(n) + ... + cr*a(n+r) = 0, with order r >= 1.
    """
    r = len(coeffs) - 1
    if r <= 0 or len(terms) <= r:
        return False
    for n in range(len(terms) - r):
        lhs = 0
        for k, c in enumerate(coeffs):
            lhs += c * terms[n + k]
        if lhs != 0:
            return False
    return True


def _generate_from_recurrence(coeffs: list[int], init_terms: list[int], n_terms: int) -> list[int] | None:
    r = len(coeffs) - 1
    if r <= 0 or len(init_terms) < r or n_terms <= 0:
        return None
    lead = coeffs[-1]
    if lead == 0:
        return None
    out = list(init_terms[:r])
    while len(out) < n_terms:
        n = len(out) - r
        lhs = 0
        for k, c in enumerate(coeffs[:-1]):
            lhs += c * out[n + k]
        rhs_num = -lhs
        if rhs_num % lead != 0:
            return None
        out.append(rhs_num // lead)
    return out


def _probe_sequence_ids(
    terms: list[int],
    db_path: Path,
    *,
    limit: int,
    min_match_length: int = 5,
) -> list[str]:
    if len(terms) < min_match_length:
        return []
    q = SequenceQuery(terms=list(terms), min_match_length=min_match_length, allow_subsequence=False)
    hits = match_exact_db(q, db_path, limit=limit, snippet_len=None)
    return [m.id for m in hits]


def discover_candidate_ids(
    query_terms: list[int],
    db_path: Path,
    *,
    limit: int = 20,
    max_time_s: float | None = None,
    tools: tuple[str, ...] = ("sympy",),
    deadline_s: float | None = None,
    time_fn: Callable[[], float] = time.perf_counter,
) -> DiscoveryResult:
    """
    Optional symbolic/numeric candidate discovery provider.

    Current implementation is SymPy-backed and does:
    - linear recurrence guess + recurrence-basis probes,
    - closed-form guess probes (where available).
    """
    q = [int(t) for t in query_terms]
    if len(q) < 5:
        return DiscoveryResult(ids=[], provenance={}, diagnostics={"enabled": True, "reason": "query_too_short"})
    local_deadline = deadline_s
    if local_deadline is None and max_time_s is not None:
        try:
            cap = float(max_time_s)
        except (TypeError, ValueError):
            cap = None
        if cap is not None:
            local_deadline = time_fn() if cap <= 0 else (time_fn() + cap)

    ids: list[str] = []
    provenance: dict[str, list[str]] = {}
    probes = 0
    rec_expr_text = None
    formula_count = 0

    def _time_up() -> bool:
        return local_deadline is not None and time_fn() >= local_deadline

    def _add_ids(found_ids: list[str], reason: str) -> None:
        for sid in found_ids:
            if sid not in ids:
                ids.append(sid)
            reasons = provenance.setdefault(sid, [])
            if reason not in reasons:
                reasons.append(reason)

    if "sympy" not in {t.strip().lower() for t in tools if t.strip()}:
        return DiscoveryResult(
            ids=[],
            provenance={},
            diagnostics={"enabled": True, "reason": "sympy_disabled", "tools": list(tools)},
        )

    if _time_up():
        return DiscoveryResult(
            ids=[],
            provenance={},
            diagnostics={"enabled": True, "tools": list(tools), "time_capped": True},
        )

    try:
        import sys

        # A broken editable Sage installation can register a meta finder that
        # rebuilds Sage for unrelated lazy imports. SymPy does not need it;
        # restore the finder after this discovery pass completes.
        meta_path = sys.meta_path[:]
        sys.meta_path[:] = [
            finder for finder in meta_path if type(finder).__module__ != "_sagemath_editable_loader"
        ]
        from sympy import Function, Symbol, Poly
        from sympy.concrete.guess import find_simple_recurrence, guess
        from sympy.core.function import AppliedUndef
    except Exception as exc:
        if "meta_path" in locals():
            sys.meta_path[:] = meta_path
        return DiscoveryResult(
            ids=[],
            provenance={},
            diagnostics={"enabled": True, "reason": "sympy_unavailable", "error": str(exc)},
        )

    if not _time_up():
        try:
            n = Symbol("n", integer=True)
            a = Function("a")
            rec_expr = find_simple_recurrence(q, A=a, N=n)
            if rec_expr is not None:
                rec_expr_text = str(rec_expr)
                coeffs_by_shift: dict[int, int] = {}
                ok = True
                for term in rec_expr.expand().as_ordered_terms():
                    coef, rest = term.as_coeff_Mul()
                    app = next((node for node in rest.atoms(AppliedUndef) if node.func == a), None)
                    if app is None:
                        ok = False
                        break
                    shift_expr = (app.args[0] - n).simplify()
                    if not shift_expr.is_integer:
                        ok = False
                        break
                    shift = int(shift_expr)
                    coeffs_by_shift[shift] = int(coeffs_by_shift.get(shift, 0) + int(coef))
                if ok and coeffs_by_shift:
                    min_shift = min(coeffs_by_shift)
                    max_shift = max(coeffs_by_shift)
                    if min_shift == 0 and max_shift >= 1:
                        coeffs = [int(coeffs_by_shift.get(k, 0)) for k in range(max_shift + 1)]
                        if _fits_linear_recurrence(coeffs, q):
                            # Probe sequence generated from observed initial conditions.
                            gen_main = _generate_from_recurrence(coeffs, q[:max_shift], max(12, len(q)))
                            if gen_main:
                                probes += 1
                                _add_ids(_probe_sequence_ids(gen_main, db_path, limit=max(3, limit // 3)), "sympy:recurrence_main")
                            # Probe basis sequences for the same recurrence.
                            for basis_i in range(max_shift):
                                if _time_up():
                                    break
                                init = [0] * max_shift
                                init[basis_i] = 1
                                gen_basis = _generate_from_recurrence(coeffs, init, max(12, len(q)))
                                if not gen_basis:
                                    continue
                                probes += 1
                                _add_ids(
                                    _probe_sequence_ids(gen_basis, db_path, limit=max(2, limit // 4)),
                                    f"sympy:recurrence_basis_{basis_i}",
                                )
        except Exception:
            pass

    if not _time_up():
        try:
            formulas = guess(q, all=True, evaluate=True)
        except Exception:
            formulas = []
        i0 = Symbol("i0", integer=True)
        for expr in formulas or []:
            if _time_up():
                break
            try:
                poly = Poly(expr, i0)
            except Exception:
                continue
            if not poly.is_univariate:
                continue
            deg = int(poly.degree())
            if deg < 0 or deg > 6:
                continue
            formula_count += 1
            try:
                gen_terms = [int(expr.subs(i0, k)) for k in range(max(12, len(q)))]
            except Exception:
                continue
            probes += 1
            _add_ids(_probe_sequence_ids(gen_terms, db_path, limit=max(2, limit // 4)), "sympy:closed_form")

    ids = ids[: max(0, int(limit))]
    provenance = {sid: provenance.get(sid, []) for sid in ids}
    result = DiscoveryResult(
        ids=ids,
        provenance=provenance,
        diagnostics={
            "enabled": True,
            "tools": [t for t in tools],
            "probes": probes,
            "formula_guesses": formula_count,
            "recurrence": rec_expr_text,
            "hit_count": len(ids),
            "time_capped": bool(_time_up()),
        },
    )
    sys.meta_path[:] = meta_path
    return result
