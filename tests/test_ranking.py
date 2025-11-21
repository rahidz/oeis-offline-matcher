from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.query import parse_query
from oeis_matcher.ranking import rank_candidates_for_query


def _make_sample_raw(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A100100 1,2,3,4,5",
                "A100101 2,4,6,8,10",
                "A100102 5,5,5,5,5",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A100100 Naturals",
                "A100101 Twice naturals",
                "A100102 Fives",
            ]
        ),
        encoding="utf-8",
    )
    return stripped, names


def test_rank_candidates(tmp_path: Path):
    stripped, names = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, db, max_terms=10)

    query = parse_query("1,2,3,4,5")
    ranked = rank_candidates_for_query(query, db, top_k=3)
    assert ranked
    assert ranked[0].record.id == "A100101" or ranked[0].record.id == "A100100"
    # Constant sequence filtered out by first-diff invariant; top results are directional matches.
