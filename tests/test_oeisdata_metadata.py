from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.oeis_data import (
    load_formulas_from_oeisdata,
    load_keywords_from_oeisdata,
    load_metadata_from_oeisdata,
    load_offsets_from_oeisdata,
)
from oeis_matcher.storage import iter_sequences


def test_metadata_loads_actual_seq_records(tmp_path: Path):
    seq = tmp_path / "seq" / "A000"
    seq.mkdir(parents=True)
    (seq / "A000045.seq").write_text(
        "%I A000045 M0692\n"
        "%N A000045 Fibonacci numbers.\n"
        "%K A000045 nonn,core,easy\n"
        "%O A000045 0,4\n"
        "%F A000045 a(n) = a(n-1) + a(n-2).\n"
        "%F A000045 a(0) = 0.\n",
        encoding="utf-8",
    )
    expected = (
        {"A000045": ["nonn", "core", "easy"]},
        {"A000045": (0, 4)},
        {"A000045": "a(n) = a(n-1) + a(n-2).\na(0) = 0."},
    )
    assert load_metadata_from_oeisdata(tmp_path) == expected
    assert load_keywords_from_oeisdata(tmp_path) == expected[0]
    assert load_offsets_from_oeisdata(tmp_path) == expected[1]
    assert load_formulas_from_oeisdata(tmp_path) == expected[2]


def test_metadata_retains_aggregate_export_support(tmp_path: Path):
    seq = tmp_path / "seq"
    seq.mkdir()
    (seq / "KEYWORDS").write_text("A000045 nonn,easy\n", encoding="utf-8")
    (seq / "OFFSET").write_text("A000045 -1,2\n", encoding="utf-8")
    (seq / "FORMULA").write_text("A000045 a(n) = F_n.\n", encoding="utf-8")
    expected = ({"A000045": ["nonn", "easy"]}, {"A000045": (-1, 2)}, {"A000045": "a(n) = F_n."})
    assert load_metadata_from_oeisdata(tmp_path) == expected
    assert load_keywords_from_oeisdata(tmp_path) == expected[0]
    assert load_offsets_from_oeisdata(tmp_path) == expected[1]
    assert load_formulas_from_oeisdata(tmp_path) == expected[2]


def test_partial_aggregate_exports_preserve_other_seq_metadata(tmp_path: Path):
    seq = tmp_path / "seq" / "A700"
    seq.mkdir(parents=True)
    (seq / "A700000.seq").write_text(
        "%K A700000 nonn,more\n%O A700000 1,2\n%F A700000 a(n) = n.\n",
        encoding="utf-8",
    )
    (tmp_path / "seq" / "KEYWORDS").write_text("A700001 nonn,easy\n", encoding="utf-8")
    keywords, offsets, formulas = load_metadata_from_oeisdata(tmp_path)
    assert keywords == {"A700000": ["nonn", "more"], "A700001": ["nonn", "easy"]}
    assert offsets == {"A700000": (1, 2)}
    assert formulas == {"A700000": "a(n) = n."}


def test_build_fills_per_entry_metadata_gaps_in_one_scan(tmp_path: Path, monkeypatch):
    seq = tmp_path / "mirror" / "seq" / "A700"
    seq.mkdir(parents=True)
    for seq_id in ("A700001", "A700000"):
        (seq / f"{seq_id}.seq").write_text(
            f"%K {seq_id} nonn,more\n%O {seq_id} 1,2\n%F {seq_id} a(n) = n.\n",
            encoding="utf-8",
        )
    stripped = tmp_path / "stripped.txt"
    stripped.write_text("A700000 1,2,3\nA700001 1,2,3\n", encoding="utf-8")
    keywords = tmp_path / "keywords.txt"
    keywords.write_text("A700000 nonn,easy\n", encoding="utf-8")
    offsets = tmp_path / "offsets.txt"
    offsets.write_text("A700000 -2,1\n", encoding="utf-8")
    formulas = tmp_path / "formulas.txt"
    formulas.write_text("A700000 Explicit formula.\n", encoding="utf-8")
    opened = []
    original_open = Path.open

    def track_open(path, *args, **kwargs):
        if path.suffix == ".seq":
            opened.append(path.name)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", track_open)
    db = tmp_path / "oeis.db"
    build_index(
        stripped, None, keywords, db,
        oeisdata_root=tmp_path / "mirror", offsets_path=offsets, formulas_path=formulas,
    )
    first, second = list(iter_sequences(db))
    assert first.keywords == ["nonn", "easy"]
    assert first.offset == (-2, 1)
    assert first.formula == "Explicit formula."
    assert second.keywords == ["nonn", "more"]
    assert second.offset == (1, 2)
    assert second.formula == "a(n) = n."
    assert first.has_formula and second.has_formula
    assert opened == ["A700000.seq", "A700001.seq"]
