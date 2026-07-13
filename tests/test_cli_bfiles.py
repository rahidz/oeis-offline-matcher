from __future__ import annotations

import json
from pathlib import Path

from oeis_matcher.cli import main


def test_cli_bindex_and_bsearch_json(tmp_path: Path, capsys):
    root = tmp_path / "files" / "A000"
    root.mkdir(parents=True)
    (root / "b000045.txt").write_text("0 0\n1 1\n2 1\n3 2\n4 3\n", encoding="utf-8")
    db = tmp_path / "bfiles.db"

    rc = main(["bindex", "--files-root", str(tmp_path / "files"), "--db", str(db), "--json"])
    assert rc == 0
    idx_payload = json.loads(capsys.readouterr().out)
    assert idx_payload["files_indexed"] == 1
    assert idx_payload["manifest_rows"] == 1
    assert idx_payload["legacy_value_rows_materialized"] == 0

    rc = main(
        [
            "bsearch",
            "3",
            "--db",
            str(db),
            "--oeis-db",
            str(tmp_path / "missing-oeis.db"),
            "--limit",
            "10",
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["value"] == "3"
    assert payload["total"] == 1
    assert payload["cached"] is False
    assert payload["matches"][0]["id"] == "A000045"
    assert payload["matches"][0]["n"] == 4


def test_cli_bfetch_from_local_base_url(tmp_path: Path, capsys):
    src = tmp_path / "src" / "A222222"
    src.mkdir(parents=True)
    (src / "b222222.txt").write_text("5 99\n", encoding="utf-8")
    dest = tmp_path / "dest"

    rc = main(
        [
            "bfetch",
            "A222222",
            "--base-url",
            (tmp_path / "src").as_uri(),
            "--dest",
            str(dest),
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["downloaded"] == 1
    assert payload["failed"] == 0
    assert (dest / "A222" / "b222222.txt").read_text(encoding="utf-8") == "5 99\n"


def test_cli_bfetch_rejects_invalid_ids(tmp_path: Path, capsys):
    rc = main(["bfetch", "not_an_oeis_id", "--dest", str(tmp_path / "x")])
    assert rc == 2
    assert "No valid OEIS ids found." in capsys.readouterr().out
