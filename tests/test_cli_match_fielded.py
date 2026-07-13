from __future__ import annotations

import json
from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.cli import main


def _build_db(tmp_path: Path) -> Path:
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    keywords = tmp_path / "keywords.txt"
    formulas = tmp_path / "formulas.txt"
    stripped.write_text(
        "\n".join(
            [
                "A910001 1,1,2,3,5,8",
                "A910002 8,5,3,2,1,0",
                "A910003 2,4,6,8,10",
                "A910004 1,-1,1,-1,1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A910001 Fibonacci demo",
                "A910002 Descending demo",
                "A910003 Even numbers demo",
                "A910004 Alternating sign demo",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    keywords.write_text(
        "\n".join(
            [
                "A910001 nonn,easy,more",
                "A910002 hard,more",
                "A910003 nonn,linear",
                "A910004 sign",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    formulas.write_text(
        "\n".join(
            [
                "A910001 a(n)=a(n-1)+a(n-2)",
                "A910003 a(n)=2*n",
                "A910004 a(n)=(-1)^n",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    db = tmp_path / "oeis.db"
    build_index(stripped, names, keywords, db, formulas_path=formulas, max_terms=20)
    return db


def test_cli_match_keyword_query_space_after_colon_json(tmp_path: Path, capsys):
    db = _build_db(tmp_path)
    rc = main(["match", "keyword: more", "--db", str(db), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert [m["id"] for m in payload["matches"]] == ["A910001", "A910002"]
    assert all(m["match_type"] == "keyword" for m in payload["matches"])
    assert (payload.get("diagnostics") or {}).get("keyword_query") == "more"


def test_cli_match_fielded_id_name_formula_json(tmp_path: Path, capsys):
    db = _build_db(tmp_path)
    rc = main(["match", 'id:A910003 name:even formula:"2*n"', "--db", str(db), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert [m["id"] for m in payload["matches"]] == ["A910003"]
    diag = payload.get("diagnostics") or {}
    q = diag.get("field_query") or {}
    assert q.get("ids") == ["A910003"]
    assert q.get("name_substrings") == ["even"]
    assert q.get("formula_substrings") == ["2*n"]


def test_cli_match_fielded_invariants_and_value_constraints_json(tmp_path: Path, capsys):
    db = _build_db(tmp_path)
    rc = main(
        [
            "match",
            "keyword:nonn,more monotonic:nondecreasing sign:nonneg contains:8 excludes:-1 term@0:1 has-formula:true",
            "--db",
            str(db),
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert [m["id"] for m in payload["matches"]] == ["A910001"]


def test_cli_match_fielded_invalid_term_index(tmp_path: Path, capsys):
    db = _build_db(tmp_path)
    rc = main(["match", "term@x:1", "--db", str(db)])
    assert rc == 2
    assert "Invalid term@index filter" in capsys.readouterr().out
