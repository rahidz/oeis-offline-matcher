from __future__ import annotations

import json
from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.cli import main


def test_cli_status_json_reports_missing_paths(tmp_path: Path, capsys):
    rc = main(
        [
            "status",
            "--stripped",
            str(tmp_path / "missing_stripped.txt"),
            "--names",
            str(tmp_path / "missing_names.txt"),
            "--keywords",
            str(tmp_path / "missing_keywords.txt"),
            "--db",
            str(tmp_path / "missing.db"),
            "--metadata",
            str(tmp_path / "missing_meta.json"),
            "--json",
        ]
    )
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ready"] is False
    assert payload["freshness"]["last_sync_utc"] is None
    assert any("missing required raw files" in w for w in (payload.get("warnings") or []))


def test_cli_status_refresh_if_stale_uses_local_sources(tmp_path: Path, capsys):
    src = tmp_path / "src"
    src.mkdir()
    stripped_src = src / "stripped.txt"
    names_src = src / "names.txt"
    stripped_src.write_text("A111111 1,2,3,4,5\n", encoding="utf-8")
    names_src.write_text("A111111 Demo\n", encoding="utf-8")

    out = tmp_path / "out"
    out.mkdir()
    stripped_out = out / "stripped.txt"
    names_out = out / "names.txt"
    keywords_out = out / "keywords.txt"
    db = out / "oeis.db"
    metadata = out / "freshness.json"
    metadata.write_text('{"last_sync_utc":"2020-01-01T00:00:00Z"}', encoding="utf-8")

    rc = main(
        [
            "status",
            "--stripped",
            str(stripped_out),
            "--names",
            str(names_out),
            "--keywords",
            str(keywords_out),
            "--db",
            str(db),
            "--metadata",
            str(metadata),
            "--stripped-url",
            stripped_src.as_uri(),
            "--names-url",
            names_src.as_uri(),
            "--max-age-days",
            "30",
            "--refresh-if-stale",
            "--json",
        ]
    )
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    refresh = payload.get("refresh") or {}
    assert refresh.get("attempted") is True
    assert refresh.get("ok") is True
    assert payload["ready"] is True
    assert db.exists()


def test_cli_warns_on_stale_data_for_match(tmp_path: Path, capsys, monkeypatch):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text("A222222 1,2,3,4,5\n", encoding="utf-8")
    names.write_text("A222222 Demo\n", encoding="utf-8")
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=8)

    metadata = tmp_path / "freshness.json"
    metadata.write_text('{"last_sync_utc":"2020-01-01T00:00:00Z"}', encoding="utf-8")

    cfg = tmp_path / "config.toml"
    cfg.write_text(
        f"""
[paths]
stripped = "{str(stripped)}"
names = "{str(names)}"
keywords = "{str(tmp_path / 'keywords.txt')}"
db = "{str(db)}"

[freshness]
max_age_days = 30
metadata_path = "{str(metadata)}"
warn_on_stale = true
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("OEIS_MATCHER_CONFIG", str(cfg))

    rc = main(["match", "1,2,3", "--db", str(db)])
    assert rc == 0

    captured = capsys.readouterr()
    assert "snapshot is stale" in captured.err
