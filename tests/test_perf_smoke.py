import time
from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.api import analyze_sequence


def _mini_db(tmp_path: Path) -> Path:
    base = Path(__file__).parent / "data" / "mini_oeis"
    db = tmp_path / "oeis.db"
    build_index(base / "stripped.txt", base / "names.txt", base / "keywords.txt", db, max_terms=20)
    return db


def test_analyze_mini_perf_under_200ms(tmp_path: Path):
    db = _mini_db(tmp_path)
    start = time.perf_counter()
    res = analyze_sequence(
        "0,1,1,2,3,5",
        db_path=db,
        exact_limit=5,
        transform_limit=10,
        transform_depth=2,
        similarity=3,
        combos=3,
        combo_coeffs=(1, 2),
        combo_max_shift=1,
        combo_candidates=10,
        collect_timings=True,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 200, f"mini analyze too slow: {elapsed_ms:.1f} ms"
    assert res["diagnostics"]["timings_ms"]["exact_ms"] >= 0.0
