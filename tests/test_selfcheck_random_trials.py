from __future__ import annotations

import random
from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.selfcheck import run_random_combo_trials


def _build_random_db(tmp_path: Path, *, seed: int, n: int, length: int) -> Path:
    rng = random.Random(seed)
    sequences: dict[str, list[int]] = {}
    for i in range(n):
        sid = f"A9{i:05d}"
        terms = [rng.randint(-30, 40) for _ in range(length)]
        if all(t == 0 for t in terms):
            terms[0] = 1
        sequences[sid] = terms

    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(f"{sid} {','.join(str(t) for t in terms)}" for sid, terms in sequences.items()),
        encoding="utf-8",
    )
    names.write_text("\n".join(f"{sid} {sid} random test" for sid in sequences) + "\n", encoding="utf-8")

    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=length)
    return db


def test_selfcheck_random_combo_trials_pass_on_random_db(tmp_path: Path):
    # Ensure the selfcheck library's random combo recovery stays correct and deterministic.
    db = _build_random_db(tmp_path, seed=0, n=40, length=14)

    results, summary = run_random_combo_trials(
        db_path=db,
        trials=6,
        seed=1,
        qlen=8,
        min_length=12,
        scan_stride=1,
        pair_max_time_s=1.0,
        pairs_only=False,
        triples_only=False,
        coeffs_to_try=(-2, -1, 1, 2),
    )
    assert int(summary["fails"]) == 0, {"summary": summary, "sample": results[:2]}

