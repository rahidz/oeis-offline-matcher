from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.matcher import match_exact_db
from oeis_matcher.models import SequenceQuery


def _build_db(tmp_path: Path) -> Path:
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A800001 1,2,3,4,5",
                "A800002 10,11,12,13,14",
                "A800003 1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A800001 Starts with 1",
                "A800002 Starts with 10",
                "A800003 Just 1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=10)
    return db


def test_match_exact_db_short_prefix_does_not_false_match_10_for_1(tmp_path: Path):
    db = _build_db(tmp_path)

    q = SequenceQuery(terms=[1], min_match_length=1, allow_subsequence=False)
    hits = match_exact_db(q, db, limit=None)
    ids = {m.id for m in hits}
    assert "A800001" in ids
    assert "A800003" in ids
    assert "A800002" not in ids


def test_match_exact_db_subsequence_offset_computed_correctly(tmp_path: Path):
    db = _build_db(tmp_path)

    q = SequenceQuery(terms=[2, 3], min_match_length=1, allow_subsequence=True)
    hits = match_exact_db(q, db, limit=10)
    assert any(m.id == "A800001" and m.match_type == "subsequence" and m.offset == 1 for m in hits)
