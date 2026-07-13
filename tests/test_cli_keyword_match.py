from __future__ import annotations

import json
from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.cli import main


def _build_db(tmp_path: Path) -> Path:
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    keywords = tmp_path / "keywords.txt"
    stripped.write_text(
        "\n".join(
            [
                "A800100 1,2,3,4,5",
                "A800101 2,3,5,7,11",
                "A800102 1,1,2,3,5",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A800100 Demo one",
                "A800101 Demo two",
                "A800102 Demo three",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    keywords.write_text(
        "\n".join(
            [
                "A800100 nonn,more",
                "A800101 hard",
                "A800102 more,easy",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    db = tmp_path / "oeis.db"
    build_index(stripped, names, keywords, db, max_terms=10)
    return db


def test_cli_match_keyword_query_json(tmp_path: Path, capsys):
    db = _build_db(tmp_path)
    rc = main(["match", "keyword: more", "--db", str(db), "--json"])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    ids = [m["id"] for m in payload["matches"]]
    assert ids == ["A800100", "A800102"]
    assert all(m["match_type"] == "keyword" for m in payload["matches"])
    assert (payload.get("diagnostics") or {}).get("keyword_query") == "more"


def test_cli_match_keyword_query_invalid_syntax(tmp_path: Path, capsys):
    db = _build_db(tmp_path)
    rc = main(["match", "keyword:", "--db", str(db)])
    assert rc == 2
    assert "Invalid keyword query" in capsys.readouterr().out
