from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.cli import main


def _make_raw_with_noise(tmp_path: Path) -> tuple[Path, Path]:
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                # Low A-numbers first so unfiltered candidate fill (if any) prefers these.
                "A000001 0,0,0,0,0,0",
                "A000002 1,1,1,1,1,1",
                "A000003 2,2,2,2,2,2",
                "A000004 3,3,3,3,3,3",
                # Target triple: A100000 + A200000 + A300000
                "A100000 3,6,4,8,10,5,5,7",
                "A200000 1,1,0,4,42,9050,6965359",
                "A300000 1,10,99,999,9990,99900,999000",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A000001 Zeros",
                "A000002 Ones",
                "A000003 Twos",
                "A000004 Threes",
                "A100000 Ishango middle column",
                "A200000 Meanders",
                "A300000 Concatenation sum",
            ]
        ),
        encoding="utf-8",
    )
    return stripped, names


def test_combo_include_ids_allows_high_anumbers(tmp_path: Path, capsys):
    stripped, names = _make_raw_with_noise(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=12)

    # q = A100000 + A200000 + A300000 (first 5 terms)
    query = "5,17,103,1011,10042"

    # With very small candidate caps, the candidate bucket will not naturally contain
    # A100000/A200000/A300000. Without include-ids we should not find the triple.
    rc = main(
        [
            "combo",
            query,
            "--db",
            str(db),
            "--triples",
            "5",
            "--coeffs",
            "1",
            "--candidates",
            "2",
            "--triple-candidates",
            "2",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "Triple combinations:" not in out

    # Forcing the ids into the pool should make the triple discoverable even with tiny caps.
    rc2 = main(
        [
            "combo",
            query,
            "--db",
            str(db),
            "--triples",
            "5",
            "--coeffs",
            "1",
            "--candidates",
            "2",
            "--triple-candidates",
            "2",
            "--include-ids",
            "A100000,A200000,A300000",
        ]
    )
    assert rc2 == 0
    out2 = capsys.readouterr().out
    assert "No combinations found." not in out2
    assert "Triple combinations:" in out2
    assert "A100000" in out2
    assert "A200000" in out2
    assert "A300000" in out2
