from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Sequence

from .models import CombinationMatch, Match

FAMILY_ORDER = (
    "transform",
    "linear_pair",
    "linear_triple",
    "modclass",
    "pointwise",
    "convolution",
)


def parse_family_quotas(text: str) -> Dict[str, int]:
    """
    Parse "family=quota" pairs from a comma-separated string.

    Unknown families and malformed entries are ignored.
    """
    allowed = set(FAMILY_ORDER)
    out: Dict[str, int] = {}
    for chunk in (p.strip() for p in str(text or "").split(",")):
        if not chunk or "=" not in chunk:
            continue
        fam, raw = chunk.split("=", 1)
        fam = fam.strip().lower()
        if fam not in allowed:
            continue
        try:
            out[fam] = max(0, int(raw.strip()))
        except ValueError:
            continue
    return out


@dataclass(frozen=True)
class _Entry:
    family: str
    score: float
    length: int
    stable: str
    dedupe_key: tuple
    payload: Match | CombinationMatch


def _score(v: float | None) -> float:
    return float(v) if v is not None else 0.0


def _norm_text(txt: str | None) -> str:
    return "".join(ch for ch in str(txt or "").lower() if not ch.isspace())


def _transform_family(desc: str | None) -> tuple[str, ...]:
    text = str(desc or "").strip()
    if not text:
        return ("unknown",)
    parts = [p.strip() for p in text.split("∘") if p.strip()]
    ops: list[str] = []
    for p in parts:
        name = p.split("(", 1)[0].strip().lower()
        if name:
            ops.append(name)
    if not ops:
        return (_norm_text(text),)
    # Keep first two operators: enough to avoid most floods but still compact.
    return tuple(ops[:2])


def _transform_key(m: Match) -> tuple:
    return (
        "transform",
        m.id,
        m.match_type,
        _transform_family(m.transform_desc or m.explanation),
    )


def _combo_key(fam: str, m: CombinationMatch) -> tuple:
    t_names = tuple(m.component_transforms or tuple("id" for _ in m.ids))
    comps = list(zip(m.ids, t_names))
    comps_sorted = tuple(sorted(comps))
    if fam in {"linear_pair", "linear_triple"}:
        # Intentionally ignore coeff/shift details for diversity so a single
        # component set does not flood top-N with tiny algebraic variations.
        return ("linear", len(m.ids), comps_sorted)
    if fam == "pointwise":
        expr = _norm_text(m.expression)
        if "gcd(" in expr:
            op = "gcd"
        elif "lcm(" in expr:
            op = "lcm"
        else:
            op = "mul"
        return ("pointwise", op, comps_sorted)
    if fam == "convolution":
        expr = _norm_text(m.expression)
        op = "dirichlet" if ("⋆" in expr or "star" in expr) else "cauchy"
        return ("convolution", op, comps_sorted)
    if fam == "modclass":
        # Residue-class order matters, so keep source order.
        return ("modclass", tuple(comps))
    return (fam, comps_sorted, _norm_text(m.expression))


def _to_entries(
    *,
    transform_matches: Sequence[Match],
    family_matches: Mapping[str, Sequence[CombinationMatch]],
) -> dict[str, list[_Entry]]:
    out: dict[str, list[_Entry]] = {}

    if transform_matches:
        out["transform"] = [
            _Entry(
                family="transform",
                score=_score(m.score),
                length=int(m.length),
                stable=f"{m.id}:{m.match_type}:{_norm_text(m.transform_desc or m.explanation)}",
                dedupe_key=_transform_key(m),
                payload=m,
            )
            for m in transform_matches
        ]

    for fam, matches in family_matches.items():
        if not matches:
            continue
        out[fam] = [
            _Entry(
                family=fam,
                score=_score(m.score),
                length=int(m.length),
                stable=f"{','.join(m.ids)}:{_norm_text(m.expression)}",
                dedupe_key=_combo_key(fam, m),
                payload=m,
            )
            for m in matches
        ]

    return out


def rerank_explanations(
    *,
    transform_matches: Sequence[Match],
    family_matches: Mapping[str, Sequence[CombinationMatch]],
    limit: int | None = None,
    default_quota: int = 1,
    quotas: Mapping[str, int] | None = None,
    diversity: bool = True,
) -> tuple[list[tuple[str, Match | CombinationMatch]], dict]:
    """
    Build a ranked explanation list across transform + combination families.

    Ranking has two phases:
    1) Per-family quota pass (fairness/diversity).
    2) Global score fill for remaining slots.
    """
    raw = _to_entries(transform_matches=transform_matches, family_matches=family_matches)
    if not raw:
        return [], {
            "input_counts": {},
            "post_dedupe_counts": {},
            "quotas": {},
            "dedupe_dropped": 0,
            "selected_count": 0,
            "selected_counts": {},
            "limit": 0,
        }

    input_counts = {fam: len(v) for fam, v in raw.items()}
    staged: dict[str, list[_Entry]] = {}
    dedupe_dropped = 0

    def _sort_key(e: _Entry) -> tuple:
        return (-e.score, -e.length, e.stable)

    for fam in FAMILY_ORDER:
        arr = raw.get(fam)
        if not arr:
            continue
        arr_sorted = sorted(arr, key=_sort_key)
        if not diversity:
            staged[fam] = arr_sorted
            continue
        seen_local: set[tuple] = set()
        uniq: list[_Entry] = []
        for e in arr_sorted:
            if e.dedupe_key in seen_local:
                dedupe_dropped += 1
                continue
            seen_local.add(e.dedupe_key)
            uniq.append(e)
        if uniq:
            staged[fam] = uniq

    for fam in raw.keys():
        if fam in staged:
            continue
        arr = raw[fam]
        arr_sorted = sorted(arr, key=_sort_key)
        if not diversity:
            staged[fam] = arr_sorted
            continue
        seen_local: set[tuple] = set()
        uniq: list[_Entry] = []
        for e in arr_sorted:
            if e.dedupe_key in seen_local:
                dedupe_dropped += 1
                continue
            seen_local.add(e.dedupe_key)
            uniq.append(e)
        if uniq:
            staged[fam] = uniq

    total = sum(len(v) for v in staged.values())
    out_limit = total if (limit is None or int(limit) <= 0) else min(int(limit), total)
    quota_map = {fam: max(0, int(default_quota)) for fam in staged}
    if quotas:
        for fam, q in quotas.items():
            if fam in quota_map:
                quota_map[fam] = max(0, int(q))

    ptr = {fam: 0 for fam in staged}
    selected_counts = {fam: 0 for fam in staged}
    chosen: list[tuple[str, _Entry]] = []
    seen_global: set[tuple] = set()

    # Phase 1: family-quota pass.
    if any(q > 0 for q in quota_map.values()) and out_limit > 0:
        while len(chosen) < out_limit:
            fam_order = sorted(
                (
                    fam
                    for fam in staged
                    if selected_counts[fam] < quota_map.get(fam, 0) and ptr[fam] < len(staged[fam])
                ),
                key=lambda fam: -staged[fam][ptr[fam]].score,
            )
            if not fam_order:
                break
            progress = False
            for fam in fam_order:
                if len(chosen) >= out_limit:
                    break
                arr = staged[fam]
                i = ptr[fam]
                pick: _Entry | None = None
                while i < len(arr):
                    cand = arr[i]
                    i += 1
                    if diversity and cand.dedupe_key in seen_global:
                        dedupe_dropped += 1
                        continue
                    pick = cand
                    break
                ptr[fam] = i
                if pick is None:
                    continue
                if diversity:
                    seen_global.add(pick.dedupe_key)
                chosen.append((fam, pick))
                selected_counts[fam] += 1
                progress = True
            if not progress:
                break

    # Phase 2: global fill.
    if len(chosen) < out_limit:
        leftovers: list[tuple[str, _Entry]] = []
        for fam, arr in staged.items():
            i = ptr[fam]
            while i < len(arr):
                leftovers.append((fam, arr[i]))
                i += 1
        leftovers.sort(key=lambda it: _sort_key(it[1]) + (it[0],))
        for fam, cand in leftovers:
            if len(chosen) >= out_limit:
                break
            if diversity and cand.dedupe_key in seen_global:
                dedupe_dropped += 1
                continue
            if diversity:
                seen_global.add(cand.dedupe_key)
            chosen.append((fam, cand))
            selected_counts[fam] += 1

    selected = [(fam, e.payload) for fam, e in chosen]
    diag = {
        "input_counts": input_counts,
        "post_dedupe_counts": {fam: len(v) for fam, v in staged.items()},
        "quotas": quota_map,
        "dedupe_dropped": dedupe_dropped,
        "selected_count": len(selected),
        "selected_counts": {fam: c for fam, c in selected_counts.items() if c > 0},
        "limit": out_limit,
    }
    return selected, diag
