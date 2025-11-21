"""
Data sync utilities for OEIS exports.

Responsibilities:
- Download stripped/names (and optional keywords) files to configured paths.
- Optionally clone the oeisdata mirror for richer metadata (keywords).

Notes:
- Uses stdlib only to keep the tool easy to install anywhere.
- Download is skipped when the destination file already exists unless `force=True`.
"""

from __future__ import annotations

import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Dict, Optional

DEFAULT_STRIPPED_URL = "https://oeis.org/stripped.gz"
DEFAULT_NAMES_URL = "https://oeis.org/names.gz"
DEFAULT_OEISDATA_REPO = "https://github.com/oeis/oeisdata"


def download_file(url: str, dest: Path, *, force: bool = False, chunk_size: int = 64 * 1024) -> Dict:
    """
    Stream a file to `dest`, creating parent dirs. Returns a small status dict.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and not force:
        return {"path": dest, "status": "skipped", "bytes": dest.stat().st_size}

    try:
        with urllib.request.urlopen(url) as resp, dest.open("wb") as out:
            shutil.copyfileobj(resp, out, length=chunk_size)
    except Exception as exc:  # pragma: no cover - propagated for caller to handle
        if dest.exists() and force:
            dest.unlink(missing_ok=True)
        raise RuntimeError(f"Failed to download {url}: {exc}") from exc

    return {"path": dest, "status": "downloaded", "bytes": dest.stat().st_size}


def clone_oeisdata_repo(dest: Path, *, repo_url: str = DEFAULT_OEISDATA_REPO, force: bool = False) -> Dict:
    """
    Clone the oeisdata mirror (or alternate repo_url) into `dest`.
    """
    dest = Path(dest)
    if dest.exists():
        if force:
            shutil.rmtree(dest)
        else:
            return {"path": dest, "status": "skipped"}

    dest.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, str(dest)],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:  # pragma: no cover - surfaced to caller
        raise RuntimeError(f"git clone failed: {result.stderr.strip()}")

    return {"path": dest, "status": "cloned"}


def sync_data(
    *,
    stripped_url: Optional[str] = DEFAULT_STRIPPED_URL,
    names_url: Optional[str] = DEFAULT_NAMES_URL,
    keywords_url: Optional[str] = None,
    stripped_path: Path,
    names_path: Path,
    keywords_path: Optional[Path] = None,
    force: bool = False,
    clone_oeisdata: bool = False,
    oeisdata_path: Optional[Path] = None,
    oeisdata_url: str = DEFAULT_OEISDATA_REPO,
) -> Dict[str, Dict]:
    """
    Download OEIS exports and optionally clone oeisdata. Returns a dict of per-task statuses.
    """
    stats: Dict[str, Dict] = {}

    if stripped_url:
        stats["stripped"] = download_file(stripped_url, stripped_path, force=force)
    if names_url:
        stats["names"] = download_file(names_url, names_path, force=force)
    if keywords_url and keywords_path:
        stats["keywords"] = download_file(keywords_url, keywords_path, force=force)
    if clone_oeisdata:
        target = oeisdata_path or Path("data/raw/oeisdata")
        stats["oeisdata"] = clone_oeisdata_repo(target, repo_url=oeisdata_url, force=force)

    return stats
