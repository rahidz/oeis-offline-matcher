"""Unattended full-data refresh used by scripts/oeis-refresh."""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .bfiles import _is_lfs_pointer, build_bfile_index, fetch_bfiles, iter_bfile_paths
from .build_index import build_index
from .config import load_config
from .freshness import update_build_metadata, update_sync_metadata
from .oeis_data import load_metadata_from_oeisdata, load_names, load_stripped
from .sync import DEFAULT_NAMES_URL, DEFAULT_STRIPPED_URL, download_file


def update_mirror(repo: Path) -> None:
    # Fetching a shallow tip avoids downloading months of export history.
    # Detached checkout preserves local b-file repairs; Git refuses overlaps.
    env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1", "GIT_TERMINAL_PROMPT": "0"}
    subprocess.run(["git", "-C", str(repo), "fetch", "--depth", "1", "origin", "main"], check=True, env=env)
    subprocess.run(["git", "-C", str(repo), "switch", "--quiet", "--detach", "origin/main"], check=True, env=env)


def refresh_bfiles(repo: Path) -> dict:
    files_root = repo / "files"
    pending = [(seq_id, path) for seq_id, path in iter_bfile_paths(files_root) if _is_lfs_pointer(path)]
    print(f"[bfiles] {len(pending)} canonical files need content", flush=True)
    for start in range(0, len(pending), 256):
        batch = pending[start : start + 256]
        paths = [path.relative_to(repo).as_posix() for _, path in batch]
        fetched = subprocess.run(
            ["git", "-C", str(repo), "-c", "lfs.concurrenttransfers=2", "lfs", "fetch",
             "--include=" + ",".join(paths), "--exclude=", "origin", "HEAD"],
        )
        if fetched.returncode:
            print("[bfiles] some LFS objects unavailable; trying canonical OEIS downloads", flush=True)
        subprocess.run(["git", "-C", str(repo), "lfs", "checkout", *paths], check=True)

    remaining = [seq_id for seq_id, path in pending if _is_lfs_pointer(path)]

    def download(seq_id: str) -> dict:
        return fetch_bfiles([seq_id], dest_root=files_root)

    failed = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for completed, result in enumerate(pool.map(download, remaining), 1):
            if result["failed"]:
                failed.extend(row["id"] for row in result["files"] if row["status"] == "failed")
            if completed % 100 == 0:
                print(f"[bfiles] direct downloads {completed}/{len(remaining)}", flush=True)
    if failed:
        raise RuntimeError(f"{len(failed)} canonical b-files still unavailable: {', '.join(failed[:20])}; rerun to resume")
    return {"updated": len(pending)}


def refresh(
    cfg: dict,
    *,
    repo: Path,
    stripped_url: str = DEFAULT_STRIPPED_URL,
    names_url: str = DEFAULT_NAMES_URL,
    skip_bfiles: bool = False,
) -> dict:
    paths = {key: Path(value) for key, value in cfg["paths"].items()}
    metadata_path = Path(cfg["freshness"]["metadata_path"])
    raw = paths["stripped"].parent
    raw.mkdir(parents=True, exist_ok=True)
    print("[refresh] updating OEIS mirror", flush=True)
    update_mirror(repo)
    print("[refresh] downloading exports and extracting keywords, offsets, formulas", flush=True)
    with tempfile.TemporaryDirectory(prefix=".refresh-", dir=raw) as temporary:
        stage = Path(temporary)
        stripped, names = stage / paths["stripped"].name, stage / paths["names"].name
        keywords_path = stage / "keywords.txt"
        offsets_path, formulas_path = stage / "offsets.txt", stage / "formulas.txt"
        download_file(stripped_url, stripped)
        download_file(names_url, names)
        keywords, offsets, formulas = load_metadata_from_oeisdata(repo)
        with keywords_path.open("w", encoding="utf-8") as output:
            for seq_id, tags in sorted(keywords.items()):
                output.write(f"{seq_id} {','.join(tags)}\n")
        with offsets_path.open("w", encoding="utf-8") as output:
            for seq_id, pair in sorted(offsets.items()):
                output.write(f"{seq_id} {pair[0]},{pair[1]}\n")
        with formulas_path.open("w", encoding="utf-8") as output:
            for seq_id, text in sorted(formulas.items()):
                for line in text.splitlines():
                    output.write(f"{seq_id} {line}\n")

        titles = load_names(names)
        count = 0
        missing = []
        for record in load_stripped(stripped):
            count += 1
            if not keywords.get(record.id) or record.id not in titles:
                missing.append(record.id)
        if not count or missing:
            raise RuntimeError(
                f"Inconsistent exports: {count} sequences, {len(missing)} missing names/keywords "
                f"({', '.join(missing[:10])}); current database preserved"
            )
        print(f"[refresh] rebuilding {count} sequences", flush=True)
        stats = build_index(
            stripped, names, keywords_path, paths["db"],
            offsets_path=offsets_path, formulas_path=formulas_path,
            max_terms=cfg["limits"]["max_terms"],
        )
        for source, destination in (
            (stripped, paths["stripped"]), (names, paths["names"]),
            (keywords_path, paths["keywords"]),
            (offsets_path, raw / "offsets.txt"), (formulas_path, raw / "formulas.txt"),
        ):
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.replace(destination)

    sync_stats = {key: {"path": paths[key], "status": "downloaded"} for key in ("stripped", "names", "keywords")}
    sync_stats["oeisdata"] = {"path": repo, "status": "updated"}
    mirror_url = subprocess.check_output(["git", "-C", str(repo), "remote", "get-url", "origin"], text=True).strip()
    update_sync_metadata(
        metadata_path, stripped_source=stripped_url, names_source=names_url,
        keywords_source=mirror_url, oeisdata_source=mirror_url,
        stripped_path=paths["stripped"], names_path=paths["names"],
        keywords_path=paths["keywords"], oeisdata_path=repo, sync_stats=sync_stats,
    )
    update_build_metadata(
        metadata_path, db_path=paths["db"], stripped_path=paths["stripped"],
        names_path=paths["names"], keywords_path=paths["keywords"],
        max_terms=cfg["limits"]["max_terms"], build_stats=stats,
    )
    print(f"[refresh] main database ready: {stats['inserted']} sequences, all with keywords", flush=True)
    if not skip_bfiles:
        refresh_bfiles(repo)
        bstats = build_bfile_index(repo / "files", paths["db"].with_name("bfiles.db"), rebuild=True)
        print(f"[refresh] b-file manifest: {bstats}", flush=True)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oeisdata", type=Path, default=Path("data/raw/oeisdata"))
    parser.add_argument("--skip-bfiles", action="store_true", help="Refresh only the main database and metadata")
    args = parser.parse_args()
    refresh(load_config(), repo=args.oeisdata, skip_bfiles=args.skip_bfiles)


if __name__ == "__main__":
    main()
