from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.cli import main


def _make_raw_with_noise(tmp_path: Path) -> tuple[Path, Path]:
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                # Low A-numbers first so candidate trimming prefers these.
                "A000001 0,0,0,0,0,0",
                "A000002 1,1,1,1,1,1",
                "A000003 2,2,2,2,2,2",
                "A000004 3,3,3,3,3,3",
                # Target pair: A100000 + A200000
                "A100000 3,6,4,8,10,5,5,7",
                "A200000 1,1,0,4,42,9050,6965359",
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
            ]
        ),
        encoding="utf-8",
    )
    return stripped, names


def test_combo_expanded_finds_pair_without_candidate_pool(tmp_path: Path, capsys):
    stripped, names = _make_raw_with_noise(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=12)

    # q = A100000 + A200000 (first 5 terms)
    query = "4,7,4,12,52"

    # With very small candidate caps, the candidate list will not naturally contain
    # A100000/A200000. Without --expanded we should not find the pair.
    rc = main(
        [
            "combo",
            query,
            "--db",
            str(db),
            "--coeffs",
            "1",
            "--candidates",
            "2",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "No combinations found." in out
    assert "A100000" not in out
    assert "A200000" not in out

    # With --expanded, we should discover the pair via the DB-wide prefix index.
    rc2 = main(
        [
            "combo",
            query,
            "--db",
            str(db),
            "--coeffs",
            "1",
            "--candidates",
            "2",
            "--expanded",
            "--expanded-max-time",
            "2.0",
        ]
    )
    assert rc2 == 0
    out2 = capsys.readouterr().out
    assert "No combinations found." not in out2
    assert "A100000" in out2
    assert "A200000" in out2


def test_combo_preset_max_enables_expanded_fallback(tmp_path: Path, capsys):
    stripped, names = _make_raw_with_noise(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=12)

    # q = A100000 + A200000 (first 5 terms)
    query = "4,7,4,12,52"

    # `--preset max` should enable `--expanded` automatically, even when the
    # normal candidate-pool search is constrained to a tiny size.
    rc = main(
        [
            "combo",
            query,
            "--db",
            str(db),
            "--preset",
            "max",
            "--coeffs",
            "1",
            "--candidates",
            "2",
            "--expanded-max-time",
            "2.0",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "Pair combinations:" in out  # preset max enables --stream for combo
    assert "No combinations found." not in out
    assert "A100000" in out
    assert "A200000" in out


def test_analyze_preset_max_enables_combo_expanded_fallback(tmp_path: Path, capsys):
    stripped, names = _make_raw_with_noise(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=12)

    query = "4,7,4,12,52"

    rc = main(
        [
            "analyze",
            query,
            "--db",
            str(db),
            "--preset",
            "max",
            "--json",
            # Keep runtime tiny; we only need the combo expanded path here.
            "--tlimit",
            "0",
            "--similar",
            "0",
            "--triples",
            "0",
            "--combos",
            "5",
            "--combo-coeffs",
            "1",
            "--combo-candidates",
            "2",
            "--combo-max-shift",
            "0",
            "--combo-max-time",
            "0.1",
            "--combo-expanded-max-time",
            "2.0",
            "--pointwise-limit",
            "0",
            "--convolution-limit",
            "0",
            "--total-max-time",
            "5",
        ]
    )
    assert rc == 0

    payload = capsys.readouterr().out
    import json

    data = json.loads(payload)
    assert any(sorted(m.get("ids") or []) == ["A100000", "A200000"] for m in (data.get("combinations") or [])), data
