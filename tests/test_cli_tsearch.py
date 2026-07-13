from __future__ import annotations

import json
from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.cli import main


def test_tsearch_json_returns_success(tmp_path: Path, capsys):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A970000 1,2,3,4,5,6",
                "A970001 2,4,6,8,10,12",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text("A970000 Naturals\nA970001 Evens\n", encoding="utf-8")
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=12)

    rc = main(
        [
            "tsearch",
            "1,2,3,4,5",
            "--db",
            str(db),
            "--json",
        ]
    )
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["query"] == [1, 2, 3, 4, 5]
    assert isinstance(payload.get("matches"), list)
