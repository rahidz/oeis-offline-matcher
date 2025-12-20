from __future__ import annotations

from pathlib import Path

from oeis_matcher.build_index import build_index


class _FakeTime:
    def __init__(self):
        self.calls = 0

    def __call__(self) -> float:
        # Allow exactly one row to be processed, then "time out".
        self.calls += 1
        return 0.0 if self.calls <= 1 else 1.0


def test_prefix_index_build_respects_deadline(tmp_path: Path):
    # Regression test: expanded combo fallback builds an in-memory prefix index.
    # This build must respect a deadline/max-time so `--total-max-time` works.
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A000001 0,0,0,0,0,0",
                "A000002 1,1,1,1,1,1",
                "A000003 1,2,3,4,5,6",
                "A000004 2,4,6,8,10,12",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A000001 Zeros",
                "A000002 Ones",
                "A000003 Naturals",
                "A000004 Evens",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=12)

    import oeis_matcher.combination_search as cs

    cs._PREFIX_INDEX_CACHE.clear()
    fake_time = _FakeTime()
    idx = cs._get_prefix_index(db, 5, deadline_s=0.5, time_fn=fake_time)

    assert idx.complete is False
    # We should have at least one id in the partially built index, but not all.
    assert 0 < len(idx.ids) < 4

