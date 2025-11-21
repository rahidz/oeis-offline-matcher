from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.storage import iter_sequences


def test_keywords_are_loaded_and_stored(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    keywords = tmp_path / "keywords.txt"

    stripped.write_text("A700000 1,2,3,5\n", encoding="utf-8")
    names.write_text("A700000 Sample\n", encoding="utf-8")
    keywords.write_text("A700000 nonn,easy,test\n", encoding="utf-8")

    db = tmp_path / "oeis.db"
    build_index(stripped, names, keywords, db, max_terms=6)

    seqs = list(iter_sequences(db))
    assert seqs[0].keywords == ["nonn", "easy", "test"]
