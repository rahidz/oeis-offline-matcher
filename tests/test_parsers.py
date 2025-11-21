import io
from pathlib import Path

from oeis_matcher.oeis_data import (
    attach_titles,
    load_names,
    load_stripped,
    parse_names_line,
    parse_stripped_line,
)


def test_parse_stripped_line_basic():
    line = "A000045 0,1,1,2,3,5,8,13"
    rec = parse_stripped_line(line, max_terms=5)
    assert rec is not None
    assert rec.id == "A000045"
    assert rec.terms == [0, 1, 1, 2, 3]
    assert rec.length == 5


def test_parse_stripped_line_skips_bad_tokens():
    line = "A123456 1,2,foo,3"
    rec = parse_stripped_line(line)
    assert rec is not None
    assert rec.terms == [1, 2, 3]


def test_parse_names_line():
    line = "A000045 Fibonacci numbers"
    parsed = parse_names_line(line)
    assert parsed == ("A000045", "Fibonacci numbers")


def test_load_helpers_with_gzip(tmp_path: Path):
    stripped_path = tmp_path / "stripped.txt"
    names_path = tmp_path / "names.txt"

    stripped_path.write_text("A000010 1,1,2,2,4\nA000012 1,1,1", encoding="utf-8")
    names_path.write_text("A000010 Euler totient\nA000012 All 1's", encoding="utf-8")

    records = list(load_stripped(stripped_path, max_terms=3))
    assert [r.id for r in records] == ["A000010", "A000012"]
    assert records[0].terms == [1, 1, 2]

    titles = load_names(names_path)
    enriched = list(attach_titles(records, titles))
    assert enriched[0].name == "Euler totient"
    assert enriched[1].name == "All 1's"
