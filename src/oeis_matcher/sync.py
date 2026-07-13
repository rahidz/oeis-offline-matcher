"""
Data sync utilities for OEIS exports.

Responsibilities:
- Download stripped/names (and optional keywords) files to configured paths.
- Optionally clone the oeisdata mirror for richer metadata (keywords).

Notes:
- Uses stdlib only to keep the tool easy to install anywhere.
- Download is skipped when the destination file already exists unless `force=True`.
- Supports local file paths/URIs as sources to stay usable in sandboxed or offline environments.
"""

from __future__ import annotations

import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Dict, Optional, Union
from urllib.parse import urlparse

DEFAULT_STRIPPED_URL = "https://oeis.org/stripped.gz"
DEFAULT_NAMES_URL = "https://oeis.org/names.gz"
DEFAULT_OEISDATA_REPO = "https://github.com/oeis/oeisdata"


def _coerce_local_path(url: Union[str, Path]) -> Optional[Path]:
    """
    Return a Path if the URL points to a local file (path or file:// URI),
    otherwise None.
    """
    if isinstance(url, Path):
        return url

    parsed = urlparse(str(url))
    if parsed.scheme in ("", "file"):
        # file:///tmp/x -> /tmp/x ; bare relative paths also handled
        candidate = Path(parsed.path)
        if parsed.netloc and parsed.scheme == "file":
            # Preserve netloc for file://host/path; treat host as root prefix.
            candidate = Path(f"/{parsed.netloc}{parsed.path}")
        return candidate

    candidate_path = Path(str(url))
    return candidate_path if candidate_path.exists() else None


def download_file(url: Union[str, Path], dest: Path, *, force: bool = False, chunk_size: int = 64 * 1024) -> Dict:
    """
    Stream a file (local or remote) to `dest`, creating parent dirs. Returns a small status dict.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and not force:
        return {"path": dest, "status": "skipped", "bytes": dest.stat().st_size}

    local_src = _coerce_local_path(url)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.unlink(missing_ok=True)

    try:
        if local_src and local_src.exists():
            with local_src.open("rb") as inp, tmp.open("wb") as out:
                shutil.copyfileobj(inp, out, length=chunk_size)
        else:
            with urllib.request.urlopen(str(url)) as resp, tmp.open("wb") as out:
                shutil.copyfileobj(resp, out, length=chunk_size)
        tmp.replace(dest)
    except Exception as exc:  # pragma: no cover - propagated for caller to handle
        tmp.unlink(missing_ok=True)
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
