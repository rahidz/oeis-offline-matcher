from __future__ import annotations

import json
import random
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .api import analyze_sequence
from .combination_search import (
    search_convolution_two_sequence_combinations,
    search_pointwise_two_sequence_combinations,
    search_three_sequence_combinations,
    search_two_sequence_combinations_expanded,
)
from .models import SequenceQuery
from .storage import get_sequence_by_id


@dataclass(frozen=True)
class RegressionCaseResult:
    name: str
    ok: bool
    elapsed_s: float
    details: dict[str, Any]


@dataclass(frozen=True)
class RandomComboTrialResult:
    kind: str  # "pair" | "triple" | "pointwise_mul" | "cauchy" | "dirichlet"
    ok: bool
    elapsed_s: float
    expression: str
    details: dict[str, Any]


def _contains_ids(matches: Iterable[dict], ids: list[str], *, order_matters: bool = False) -> bool:
    want = list(ids)
    for m in matches or []:
        got = list(m.get("ids") or [])
        if order_matters:
            if got == want:
                return True
        else:
            if sorted(got) == sorted(want):
                return True
    return False


def load_regression_cases(path: str | Path) -> list[dict]:
    p = Path(path)
    data = json.loads(p.read_text())
    if not isinstance(data, list):
        raise ValueError(f"Expected a list of cases in {p}")
    return data


def run_regressions(
    *,
    db_path: str | Path,
    cases_path: str | Path,
    fail_fast: bool = False,
) -> tuple[list[RegressionCaseResult], dict[str, Any]]:
    cases = load_regression_cases(cases_path)
    db = Path(db_path)

    results: list[RegressionCaseResult] = []
    passes = 0
    fails = 0
    skips = 0

    for case in cases:
        name = str(case.get("name") or "(unnamed)")
        query = str(case.get("query") or "")
        opts = dict(case.get("opts") or {})
        expect = dict(case.get("expect") or {})
        required_ids = [str(seq_id) for seq_id in case.get("requires_ids") or ()]
        missing_ids = [seq_id for seq_id in required_ids if get_sequence_by_id(db, seq_id) is None]
        if missing_ids:
            skips += 1
            results.append(
                RegressionCaseResult(
                    name=name,
                    ok=True,
                    elapsed_s=0.0,
                    details={"skipped": True, "missing_required_ids": missing_ids},
                )
            )
            continue

        t0 = time.perf_counter()
        res = analyze_sequence(query, db_path=db, collect_timings=True, **opts)
        elapsed_s = time.perf_counter() - t0

        ok = True
        reasons: list[str] = []

        if "exact_top" in expect:
            top = res["exact_matches"][0]["id"] if res.get("exact_matches") else None
            if top != expect["exact_top"]:
                ok = False
                reasons.append(f"exact_top={top!r} expected {expect['exact_top']!r}")

        if "transform_contains" in expect:
            ids = {m["id"] for m in (res.get("transform_matches") or [])}
            missing = [x for x in expect["transform_contains"] if x not in ids]
            if missing:
                ok = False
                reasons.append(f"transform missing {missing}")

        if "combo_contains_ids" in expect:
            if not _contains_ids(res.get("combinations") or [], list(expect["combo_contains_ids"])):
                ok = False
                reasons.append(f"combo missing ids={expect['combo_contains_ids']}")

        if "pointwise_contains_ids" in expect:
            if not _contains_ids(res.get("pointwise_combinations") or [], list(expect["pointwise_contains_ids"])):
                ok = False
                reasons.append(f"pointwise missing ids={expect['pointwise_contains_ids']}")

        if "convolution_contains_ids" in expect:
            if not _contains_ids(res.get("convolution_combinations") or [], list(expect["convolution_contains_ids"])):
                ok = False
                reasons.append(f"convolution missing ids={expect['convolution_contains_ids']}")

        if "modclass_contains_ids" in expect:
            if not _contains_ids(res.get("modclass_combinations") or [], list(expect["modclass_contains_ids"])):
                ok = False
                reasons.append(f"modclass missing ids={expect['modclass_contains_ids']}")

        ranked_families = {str(row.get("family")) for row in res.get("ranked_explanations") or []}
        if "ranked_families_contains" in expect:
            missing = [family for family in expect["ranked_families_contains"] if family not in ranked_families]
            if missing:
                ok = False
                reasons.append(f"ranked families missing {missing}")
        if len(ranked_families) < int(expect.get("min_ranked_families", 0)):
            ok = False
            reasons.append(
                f"ranked family count={len(ranked_families)} expected >= {expect['min_ranked_families']}"
            )

        if ok:
            passes += 1
        else:
            fails += 1

        details: dict[str, Any] = {
            "query": query,
            "opts": opts,
            "expect": expect,
            "reasons": reasons,
            "timings_ms": (res.get("diagnostics") or {}).get("timings_ms"),
        }
        results.append(RegressionCaseResult(name=name, ok=ok, elapsed_s=elapsed_s, details=details))

        if fail_fast and not ok:
            break

    summary = {"cases": len(results), "passes": passes, "fails": fails, "skips": skips}
    return results, summary


def _max_id_num(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MAX(CAST(substr(id,2) AS INTEGER)) FROM sequences").fetchone()
    return int(row[0] or 0)

def _min_id_num(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MIN(CAST(substr(id,2) AS INTEGER)) FROM sequences").fetchone()
    return int(row[0] or 0)


def _pick_id(
    conn: sqlite3.Connection,
    rng: random.Random,
    *,
    min_length: int,
    stride: int = 1,
    max_tries: int = 500,
) -> str:
    """
    Pick an OEIS id like A012345 without `ORDER BY RANDOM()` (slow on big tables).
    """
    stride = max(int(stride), 1)
    min_num = _min_id_num(conn)
    max_num = _max_id_num(conn)
    if max_num <= 0:
        raise RuntimeError("No sequences found in DB (is the index built?)")

    for _ in range(max_tries):
        # Choose a random multiple of `stride` within the numeric A-number range.
        # Use ceil(min/stride) so `probe` isn't always below the true minimum.
        kmin = (min_num + stride - 1) // stride
        kmax = max_num // stride
        if kmax < kmin:
            kmax = kmin
        k = rng.randint(kmin, max(kmax, kmin))
        start = k * stride
        probe = f"A{start:06d}"
        if stride == 1:
            row = conn.execute(
                "SELECT id FROM sequences WHERE id >= ? AND length >= ? ORDER BY id LIMIT 1",
                (probe, int(min_length)),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM sequences WHERE id >= ? AND length >= ? AND (CAST(substr(id,2) AS INTEGER) % ?) = 0 ORDER BY id LIMIT 1",
                (probe, int(min_length), stride),
            ).fetchone()
        if row and row[0]:
            return str(row[0])
    raise RuntimeError(f"Failed to pick an id after {max_tries} tries (min_length={min_length}, stride={stride})")


def _terms(seq_id: str, db_path: Path, n: int) -> list[int]:
    rec = get_sequence_by_id(db_path, seq_id)
    if not rec:
        raise RuntimeError(f"Missing id in DB: {seq_id}")
    if len(rec.terms) < n:
        raise RuntimeError(f"Sequence too short for {n} terms: {seq_id} has {len(rec.terms)} terms")
    return rec.terms[:n]


def _is_degenerate(values: list[int], *, min_distinct: int = 4) -> bool:
    if not values:
        return True
    if len(set(values)) < min_distinct:
        return True
    if all(v == 0 for v in values):
        return True
    return False


def run_random_combo_trials(
    *,
    db_path: str | Path,
    trials: int,
    pointwise_trials: int = 0,
    convolution_trials: int = 0,
    seed: int = 0,
    qlen: int = 8,
    min_length: int = 30,
    scan_stride: int = 100,
    pair_max_time_s: float = 6.0,
    pointwise_max_time_s: float = 0.75,
    convolution_max_time_s: float = 0.75,
    pairs_only: bool = False,
    triples_only: bool = False,
    coeffs_to_try: Iterable[int] = (-5, -4, -3, -2, -1, 1, 2, 3, 4, 5),
) -> tuple[list[RandomComboTrialResult], dict[str, Any]]:
    """
    Random sanity checks on a built OEIS DB.

    - Pair trials use the expanded (DB-wide prefix index) pair solver and try to recover
      the exact generating identity.
    - Triple trials use a bucket containing only the chosen triple, so recovery should
      be deterministic (tests coefficient/verification logic).
    """
    db = Path(db_path)
    rng = random.Random(int(seed))
    qlen = int(qlen)
    if qlen < 5:
        raise ValueError("--qlen should be >= 5 (expanded search uses a 5-term prefix key)")

    coeffs_list = [int(c) for c in coeffs_to_try if int(c) != 0]
    if not coeffs_list:
        raise ValueError("coeffs_to_try must include at least one nonzero coefficient")

    do_pairs = not triples_only
    do_triples = not pairs_only

    results: list[RandomComboTrialResult] = []
    ok_total = 0
    fail_total = 0

    with sqlite3.connect(db) as conn:
        for _i in range(int(trials)):
            if do_pairs:
                # Resample until the constructed query isn't too degenerate; otherwise there may be
                # many valid decompositions and we can miss the intended one within output limits.
                ok = False
                t0 = time.perf_counter()
                details: dict[str, Any] = {}
                expr = ""
                for _attempt in range(50):
                    remaining_s = float(pair_max_time_s) - (time.perf_counter() - t0)
                    if remaining_s <= 0:
                        break
                    id1 = _pick_id(conn, rng, min_length=min_length, stride=scan_stride)
                    id2 = _pick_id(conn, rng, min_length=min_length, stride=scan_stride)
                    for _ in range(50):
                        if id2 != id1:
                            break
                        id2 = _pick_id(conn, rng, min_length=min_length, stride=scan_stride)
                    if id2 == id1:
                        raise RuntimeError("Failed to pick two distinct ids for a pair trial")

                    a, b = rng.choice(coeffs_list), rng.choice(coeffs_list)
                    if a == 0 or b == 0:
                        continue

                    s1 = _terms(id1, db, qlen)
                    s2 = _terms(id2, db, qlen)
                    q = [a * x + b * y for x, y in zip(s1, s2)]
                    if _is_degenerate(q):
                        continue

                    query = SequenceQuery(terms=q, min_match_length=min(5, qlen), allow_subsequence=False)
                    matches = search_two_sequence_combinations_expanded(
                        query,
                        db,
                        coeffs=coeffs_list,
                        limit=200,
                        scan_strides=(int(scan_stride), 1) if int(scan_stride) > 1 else (1,),
                        max_time_s=remaining_s,
                        snippet_len=None,
                        # Avoid dropping the intended generating identity when the
                        # chosen (id1,id2) pair admits multiple coefficient solutions
                        # (rare but can happen on short prefixes).
                        dedupe_family=False,
                    )

                    want = {id1: a, id2: b}
                    ok = False
                    for m in matches:
                        got = {m.ids[0]: int(m.coeffs[0]), m.ids[1]: int(m.coeffs[1])}
                        if got == want:
                            ok = True
                            expr = m.expression
                            break
                    details = {"id1": id1, "id2": id2, "coeffs": (a, b), "query": q[:10]}
                    if ok:
                        break

                elapsed_s = time.perf_counter() - t0
                results.append(
                    RandomComboTrialResult(
                        kind="pair",
                        ok=ok,
                        elapsed_s=elapsed_s,
                        expression=expr or "(no match)",
                        details=details,
                    )
                )
                if ok:
                    ok_total += 1
                else:
                    fail_total += 1

            if do_triples:
                t0 = time.perf_counter()
                id1 = _pick_id(conn, rng, min_length=min_length, stride=1)
                id2 = _pick_id(conn, rng, min_length=min_length, stride=1)
                id3 = _pick_id(conn, rng, min_length=min_length, stride=1)
                ids = list(dict.fromkeys([id1, id2, id3]))
                while len(ids) < 3:
                    ids.append(_pick_id(conn, rng, min_length=min_length, stride=1))
                    ids = list(dict.fromkeys(ids))
                id1, id2, id3 = ids[:3]

                a, b, c = (rng.choice(coeffs_list) for _ in range(3))
                if a == 0 or b == 0 or c == 0:
                    # should not happen due to coeffs_list filtering, but keep guard
                    a, b, c = 1, 1, 1

                rec1 = get_sequence_by_id(db, id1)
                rec2 = get_sequence_by_id(db, id2)
                rec3 = get_sequence_by_id(db, id3)
                if not rec1 or not rec2 or not rec3:
                    raise RuntimeError("Missing one of the chosen triple ids in DB")
                if min(len(rec1.terms), len(rec2.terms), len(rec3.terms)) < qlen:
                    continue
                q = [a * rec1.terms[i] + b * rec2.terms[i] + c * rec3.terms[i] for i in range(qlen)]
                if _is_degenerate(q):
                    continue
                query = SequenceQuery(terms=q, min_match_length=min(5, qlen), allow_subsequence=False)

                matches = search_three_sequence_combinations(
                    query,
                    [rec1, rec2, rec3],
                    coeffs=tuple(coeffs_list),
                    max_shift=0,
                    max_shift_back=0,
                    limit=10,
                    max_candidates=None,
                    max_checks=200_000,
                    max_time_s=2.0,
                    component_transforms=None,
                    snippet_len=None,
                    use_rational=False,
                )
                want = {id1: a, id2: b, id3: c}
                ok = False
                expr = ""
                for m in matches:
                    got = {m.ids[0]: int(m.coeffs[0]), m.ids[1]: int(m.coeffs[1]), m.ids[2]: int(m.coeffs[2])}
                    if got == want:
                        ok = True
                        expr = m.expression
                        break

                elapsed_s = time.perf_counter() - t0
                details = {"ids": [id1, id2, id3], "coeffs": (a, b, c), "query": q[:10]}
                results.append(
                    RandomComboTrialResult(
                        kind="triple",
                        ok=ok,
                        elapsed_s=elapsed_s,
                        expression=expr or "(no match)",
                        details=details,
                    )
                )
                if ok:
                    ok_total += 1
                else:
                    fail_total += 1

        # Pointwise/convolution trials are separate counts so users can opt into them
        # without inflating the runtime of the pair/triple identity recovery checks.
        for _i in range(int(pointwise_trials)):
            ok = False
            expr = ""
            details: dict[str, Any] = {}
            t0 = time.perf_counter()
            for _attempt in range(80):
                if (time.perf_counter() - t0) > float(pointwise_max_time_s):
                    break
                id1 = _pick_id(conn, rng, min_length=min_length, stride=1)
                id2 = _pick_id(conn, rng, min_length=min_length, stride=1)
                for _ in range(50):
                    if id2 != id1:
                        break
                    id2 = _pick_id(conn, rng, min_length=min_length, stride=1)
                if id2 == id1:
                    continue

                rec1 = get_sequence_by_id(db, id1)
                rec2 = get_sequence_by_id(db, id2)
                if not rec1 or not rec2:
                    continue
                if min(len(rec1.terms), len(rec2.terms)) < qlen:
                    continue

                q = [rec1.terms[i] * rec2.terms[i] for i in range(qlen)]
                if _is_degenerate(q):
                    continue

                query = SequenceQuery(terms=q, min_match_length=min(5, qlen), allow_subsequence=False)
                matches = search_pointwise_two_sequence_combinations(
                    query,
                    [rec1, rec2],
                    ops=("mul",),
                    max_shift=0,
                    max_shift_back=0,
                    limit=10,
                    max_candidates=None,
                    max_checks=50_000,
                    max_time_s=float(pointwise_max_time_s),
                    snippet_len=None,
                )
                ok = any(set(m.ids) == {id1, id2} and (m.combined_terms == q) for m in matches)
                details = {"ids": [id1, id2], "op": "mul", "query": q[:10]}
                if ok:
                    expr = next(m.expression for m in matches if set(m.ids) == {id1, id2})
                    break

            elapsed_s = time.perf_counter() - t0
            results.append(
                RandomComboTrialResult(
                    kind="pointwise_mul",
                    ok=ok,
                    elapsed_s=elapsed_s,
                    expression=expr or "(no match)",
                    details=details,
                )
            )
            if ok:
                ok_total += 1
            else:
                fail_total += 1

        for _i in range(int(convolution_trials)):
            ok = False
            expr = ""
            details: dict[str, Any] = {}
            t0 = time.perf_counter()
            for _attempt in range(80):
                if (time.perf_counter() - t0) > float(convolution_max_time_s):
                    break
                op = rng.choice(["cauchy", "dirichlet"])
                id1 = _pick_id(conn, rng, min_length=min_length, stride=1)
                id2 = _pick_id(conn, rng, min_length=min_length, stride=1)
                for _ in range(50):
                    if id2 != id1:
                        break
                    id2 = _pick_id(conn, rng, min_length=min_length, stride=1)
                if id2 == id1:
                    continue

                rec1 = get_sequence_by_id(db, id1)
                rec2 = get_sequence_by_id(db, id2)
                if not rec1 or not rec2:
                    continue
                if min(len(rec1.terms), len(rec2.terms)) < qlen:
                    continue

                if op == "cauchy":
                    q: list[int] = []
                    for n in range(qlen):
                        s = 0
                        for k in range(n + 1):
                            s += rec1.terms[k] * rec2.terms[n - k]
                        q.append(s)
                else:
                    q = []
                    for n in range(1, qlen + 1):
                        s = 0
                        for d in range(1, n + 1):
                            if n % d != 0:
                                continue
                            i = d - 1
                            j = n // d - 1
                            if i < len(rec1.terms) and j < len(rec2.terms):
                                s += rec1.terms[i] * rec2.terms[j]
                        q.append(s)

                if _is_degenerate(q):
                    continue

                query = SequenceQuery(terms=q, min_match_length=min(5, qlen), allow_subsequence=False)
                matches = search_convolution_two_sequence_combinations(
                    query,
                    [rec1, rec2],
                    ops=(op,),
                    max_length=max(32, qlen),
                    limit=10,
                    max_candidates=None,
                    max_checks=50_000,
                    max_time_s=float(convolution_max_time_s),
                    snippet_len=None,
                )
                ok = any(set(m.ids) == {id1, id2} and (m.combined_terms == q) for m in matches)
                details = {"ids": [id1, id2], "op": op, "query": q[:10]}
                if ok:
                    expr = next(m.expression for m in matches if set(m.ids) == {id1, id2})
                    break

            elapsed_s = time.perf_counter() - t0
            results.append(
                RandomComboTrialResult(
                    kind=str(details.get("op") or "convolution"),
                    ok=ok,
                    elapsed_s=elapsed_s,
                    expression=expr or "(no match)",
                    details=details,
                )
            )
            if ok:
                ok_total += 1
            else:
                fail_total += 1

    summary = {"trials": len(results), "passes": ok_total, "fails": fail_total}
    return results, summary
