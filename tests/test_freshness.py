from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.freshness import build_status_report, update_build_metadata, update_sync_metadata


def _mini_inputs(tmp_path: Path) -> tuple[Path, Path]:
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text("A123456 1,2,3,4,5,6\n", encoding="utf-8")
    names.write_text("A123456 Demo\n", encoding="utf-8")
    return stripped, names


def test_update_sync_metadata_persists_snapshot_markers(tmp_path: Path):
    stripped, names = _mini_inputs(tmp_path)
    keywords = tmp_path / "keywords.txt"
    keywords.write_text("A123456 nonn\n", encoding="utf-8")

    meta_path = tmp_path / "freshness.json"
    payload = update_sync_metadata(
        meta_path,
        stripped_source="file:///tmp/stripped.txt",
        names_source="file:///tmp/names.txt",
        keywords_source="file:///tmp/keywords.txt",
        oeisdata_source=None,
        stripped_path=stripped,
        names_path=names,
        keywords_path=keywords,
        oeisdata_path=None,
        sync_stats={"stripped": {"status": "downloaded", "path": stripped}},
        now=datetime(2026, 2, 10, 12, 0, tzinfo=timezone.utc),
    )

    assert payload["last_sync_utc"] == "2026-02-10T12:00:00Z"
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    assert data["sync"]["artifacts"]["stripped"]["exists"] is True
    assert data["sync"]["artifacts"]["names"]["exists"] is True
    assert data["sync"]["sources"]["stripped"] == "file:///tmp/stripped.txt"
    assert data["sync"]["content_updated"] is True


def test_skipped_sync_does_not_make_old_snapshot_fresh(tmp_path: Path):
    stripped, names = _mini_inputs(tmp_path)
    meta_path = tmp_path / "freshness.json"
    update_sync_metadata(
        meta_path,
        stripped_source="dummy",
        names_source="dummy",
        keywords_source=None,
        oeisdata_source=None,
        stripped_path=stripped,
        names_path=names,
        keywords_path=None,
        oeisdata_path=None,
        sync_stats={"stripped": {"status": "downloaded"}},
        now=datetime(2025, 12, 1, tzinfo=timezone.utc),
    )
    payload = update_sync_metadata(
        meta_path,
        stripped_source="dummy",
        names_source="dummy",
        keywords_source=None,
        oeisdata_source=None,
        stripped_path=stripped,
        names_path=names,
        keywords_path=None,
        oeisdata_path=None,
        sync_stats={
            "stripped": {"status": "skipped"},
            "names": {"status": "skipped"},
        },
        now=datetime(2026, 2, 14, tzinfo=timezone.utc),
    )

    assert payload["last_sync_utc"] == "2025-12-01T00:00:00Z"
    assert payload["sync"]["timestamp_utc"] == "2026-02-14T00:00:00Z"
    assert payload["sync"]["content_updated"] is False


def test_build_status_report_flags_stale_from_metadata(tmp_path: Path):
    stripped, names = _mini_inputs(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=12)

    meta_path = tmp_path / "freshness.json"
    update_sync_metadata(
        meta_path,
        stripped_source="dummy",
        names_source="dummy",
        keywords_source=None,
        oeisdata_source=None,
        stripped_path=stripped,
        names_path=names,
        keywords_path=tmp_path / "missing_keywords.txt",
        oeisdata_path=None,
        sync_stats={"stripped": {"status": "downloaded"}},
        now=datetime(2025, 12, 1, 0, 0, tzinfo=timezone.utc),
    )
    update_build_metadata(
        meta_path,
        db_path=db,
        stripped_path=stripped,
        names_path=names,
        keywords_path=tmp_path / "missing_keywords.txt",
        max_terms=12,
        build_stats={"inserted": 1},
        now=datetime(2025, 12, 1, 0, 1, tzinfo=timezone.utc),
    )

    report = build_status_report(
        stripped_path=stripped,
        names_path=names,
        keywords_path=tmp_path / "missing_keywords.txt",
        db_path=db,
        metadata_path=meta_path,
        max_age_days=30,
        now=datetime(2026, 2, 14, 0, 0, tzinfo=timezone.utc),
    )

    assert report["freshness"]["is_stale"] is True
    assert report["freshness"]["last_sync_source"] == "metadata"
    assert (report["freshness"].get("age_days") or 0) > 60


def test_build_status_report_falls_back_to_file_mtime(tmp_path: Path):
    stripped, names = _mini_inputs(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, max_terms=12)

    # Force raw files to an old mtime so stale detection can run without metadata.
    old_ts = 1704067200  # 2024-01-01T00:00:00Z
    os.utime(stripped, (old_ts, old_ts))
    os.utime(names, (old_ts, old_ts))

    report = build_status_report(
        stripped_path=stripped,
        names_path=names,
        keywords_path=tmp_path / "missing_keywords.txt",
        db_path=db,
        metadata_path=tmp_path / "missing_meta.json",
        max_age_days=30,
        now=datetime(2026, 2, 14, 0, 0, tzinfo=timezone.utc),
    )

    assert report["freshness"]["last_sync_source"] == "file_mtime"
    assert report["freshness"]["is_stale"] is True
