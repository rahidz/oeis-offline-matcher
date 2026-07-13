"""
Freshness metadata and environment health helpers.

This module stores lightweight sync/build metadata and provides a status report
used by `oeis status` and stale-data guardrails.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
from typing import Any


def _utc_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _to_iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_iso_utc(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        value = text.strip()
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
    except Exception:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


def file_marker(path: Path | None) -> dict[str, Any]:
    marker: dict[str, Any] = {"path": str(path) if path is not None else "", "exists": False}
    if path is None:
        return marker
    p = Path(path)
    marker["path"] = str(p)
    if not p.exists():
        return marker
    st = p.stat()
    marker.update(
        {
            "exists": True,
            "bytes": int(st.st_size),
            "mtime_utc": _to_iso_utc(datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)),
        }
    )
    return marker


def repo_marker(path: Path | None) -> dict[str, Any]:
    marker = file_marker(path)
    if path is None:
        return marker
    repo = Path(path)
    if not (repo / ".git").exists():
        return marker
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode == 0:
            marker["head"] = proc.stdout.strip()
    except Exception:
        pass
    return marker


def read_metadata(metadata_path: Path) -> dict[str, Any]:
    path = Path(metadata_path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"invalid metadata file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"invalid metadata file {path}: expected a JSON object")
    return data


def write_metadata(metadata_path: Path, payload: dict[str, Any]) -> None:
    path = Path(metadata_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(_json_safe(payload), indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def update_sync_metadata(
    metadata_path: Path,
    *,
    stripped_source: str | None,
    names_source: str | None,
    keywords_source: str | None,
    oeisdata_source: str | None,
    stripped_path: Path,
    names_path: Path,
    keywords_path: Path | None,
    oeisdata_path: Path | None,
    sync_stats: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    try:
        payload = read_metadata(metadata_path)
    except RuntimeError:
        payload = {}

    ts = _to_iso_utc(_utc_now(now))
    statuses = {
        str(result.get("status") or "")
        for result in sync_stats.values()
        if isinstance(result, dict)
    }
    content_updated = bool(statuses - {"", "skipped"})
    payload["schema_version"] = 1
    if content_updated:
        payload["last_sync_utc"] = ts
    payload["sync"] = {
        "timestamp_utc": ts,
        "content_updated": content_updated,
        "sources": {
            "stripped": stripped_source,
            "names": names_source,
            "keywords": keywords_source,
            "oeisdata": oeisdata_source,
        },
        "artifacts": {
            "stripped": file_marker(stripped_path),
            "names": file_marker(names_path),
            "keywords": file_marker(keywords_path),
            "oeisdata": repo_marker(oeisdata_path),
        },
        "results": _json_safe(sync_stats),
    }
    write_metadata(metadata_path, payload)
    return payload


def update_build_metadata(
    metadata_path: Path,
    *,
    db_path: Path,
    stripped_path: Path,
    names_path: Path | None,
    keywords_path: Path | None,
    max_terms: int | None,
    build_stats: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    try:
        payload = read_metadata(metadata_path)
    except RuntimeError:
        payload = {}

    ts = _to_iso_utc(_utc_now(now))
    payload.update(
        {
            "schema_version": 1,
            "last_build_utc": ts,
            "build": {
                "timestamp_utc": ts,
                "max_terms": int(max_terms) if max_terms is not None else None,
                "sources": {
                    "stripped": file_marker(stripped_path),
                    "names": file_marker(names_path),
                    "keywords": file_marker(keywords_path),
                },
                "db": file_marker(db_path),
                "results": _json_safe(build_stats),
            },
        }
    )
    write_metadata(metadata_path, payload)
    return payload


def _db_health(db_path: Path) -> dict[str, Any]:
    info = file_marker(db_path)
    info.update(
        {
            "ok": False,
            "sequence_count": None,
            "missing_recommended_indexes": [],
            "error": None,
        }
    )
    if not info.get("exists"):
        info["error"] = "missing"
        return info

    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM sequences").fetchone()
            info["sequence_count"] = int(row[0]) if row else 0
        from .storage import missing_recommended_indexes

        info["missing_recommended_indexes"] = missing_recommended_indexes(db_path)
        info["ok"] = True
    except Exception as exc:
        info["error"] = str(exc)

    return info


def build_status_report(
    *,
    stripped_path: Path,
    names_path: Path,
    keywords_path: Path,
    db_path: Path,
    metadata_path: Path,
    max_age_days: float,
    now: datetime | None = None,
    include_db_checks: bool = True,
) -> dict[str, Any]:
    now_dt = _utc_now(now)
    metadata_error: str | None = None
    metadata: dict[str, Any]
    try:
        metadata = read_metadata(metadata_path)
    except RuntimeError as exc:
        metadata = {}
        metadata_error = str(exc)

    stripped = file_marker(stripped_path)
    names = file_marker(names_path)
    keywords = file_marker(keywords_path)

    db = _db_health(db_path) if include_db_checks else file_marker(db_path)

    last_sync_text = metadata.get("last_sync_utc") if isinstance(metadata, dict) else None
    last_sync_dt = _parse_iso_utc(last_sync_text if isinstance(last_sync_text, str) else None)
    last_sync_source = "metadata"

    if last_sync_dt is None:
        fallback_times: list[datetime] = []
        for marker in (stripped, names):
            dt = _parse_iso_utc(marker.get("mtime_utc") if isinstance(marker.get("mtime_utc"), str) else None)
            if dt is not None:
                fallback_times.append(dt)
        if fallback_times:
            last_sync_dt = min(fallback_times)
            last_sync_source = "file_mtime"

    age_days: float | None = None
    if last_sync_dt is not None:
        age_days = max(0.0, (now_dt - last_sync_dt).total_seconds() / 86400.0)

    stale = bool(age_days is not None and age_days > float(max_age_days))

    missing_required = [
        label
        for label, marker in (("stripped", stripped), ("names", names))
        if not bool(marker.get("exists"))
    ]

    warnings: list[str] = []
    if metadata_error:
        warnings.append(metadata_error)
    if stale:
        age_txt = f"{age_days:.1f}d" if age_days is not None else "unknown"
        warnings.append(f"data snapshot is stale (age={age_txt}, threshold={max_age_days}d)")
    if missing_required:
        warnings.append(f"missing required raw files: {', '.join(missing_required)}")
    if include_db_checks and not bool(db.get("exists")):
        warnings.append("missing index DB")
    if include_db_checks and db.get("error") and db.get("error") != "missing":
        warnings.append(f"db health check error: {db.get('error')}")
    if include_db_checks and db.get("missing_recommended_indexes"):
        missing = db.get("missing_recommended_indexes") or []
        warnings.append(f"db missing recommended indexes: {', '.join(missing)}")

    ready = (not missing_required) and bool(db.get("exists"))
    if include_db_checks and db.get("error") and db.get("error") != "missing":
        ready = False

    return {
        "schema_version": 1,
        "generated_utc": _to_iso_utc(now_dt),
        "ready": bool(ready),
        "paths": {
            "stripped": stripped,
            "names": names,
            "keywords": keywords,
            "db": db,
            "metadata": file_marker(metadata_path),
        },
        "freshness": {
            "max_age_days": float(max_age_days),
            "last_sync_utc": _to_iso_utc(last_sync_dt) if last_sync_dt else None,
            "last_sync_source": last_sync_source,
            "age_days": age_days,
            "is_stale": stale,
        },
        "metadata": {
            "exists": bool(file_marker(metadata_path).get("exists")),
            "path": str(metadata_path),
            "error": metadata_error,
            "last_sync_utc": metadata.get("last_sync_utc"),
            "last_build_utc": metadata.get("last_build_utc"),
            "sync": metadata.get("sync"),
            "build": metadata.get("build"),
        },
        "warnings": warnings,
    }
