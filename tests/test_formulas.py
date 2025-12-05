from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.oeis_data import parse_formula_line, load_formulas
from oeis_matcher.storage import iter_sequences


def test_parse_formula_line_basic():
    line = "A000045 a(n) = Fibonacci(n)"
    parsed = parse_formula_line(line)
    assert parsed == ("A000045", "a(n) = Fibonacci(n)")


def test_load_formulas_combines_lines(tmp_path: Path):
    content = "\n".join(
        [
            "A000045 a(n)=F_n",
            "A000045 also equals round(phi^n/sqrt(5))",
            "A000142 a(n)=n!",
        ]
    )
    formula_file = tmp_path / "FORMULA"
    formula_file.write_text(content, encoding="utf-8")

    formulas = load_formulas(formula_file)
    assert formulas["A000045"].count("\n") == 1  # combined lines
    assert "round(phi" in formulas["A000045"]
    assert "n!" in formulas["A000142"]


def test_build_index_ingests_formula_text(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    formulas = tmp_path / "FORMULA"

    stripped.write_text("A123456 1,1,2,3,5\n", encoding="utf-8")
    names.write_text("A123456 Sample seq\n", encoding="utf-8")
    formulas.write_text("A123456 a(n)=Fibonacci(n)\n", encoding="utf-8")

    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, formulas_path=formulas, max_terms=8)

    recs = list(iter_sequences(db))
    assert recs[0].formula == "a(n)=Fibonacci(n)"
    assert recs[0].has_formula is True
