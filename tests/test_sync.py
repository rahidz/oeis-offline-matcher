import subprocess
import threading
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.storage import iter_sequences
from oeis_matcher.sync import sync_data


@contextmanager
def serve_directory(directory: Path):
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        yield base_url
    finally:
        httpd.shutdown()
        thread.join(timeout=2)


def test_sync_downloads_and_skips_existing(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "stripped.gz").write_text("SAMPLE_STRIPPED", encoding="utf-8")
    (src / "names.gz").write_text("SAMPLE_NAMES", encoding="utf-8")

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with serve_directory(src) as base:
        stats = sync_data(
            stripped_url=f"{base}/stripped.gz",
            names_url=f"{base}/names.gz",
            stripped_path=out_dir / "stripped.gz",
            names_path=out_dir / "names.gz",
            force=False,
        )
        assert stats["stripped"]["status"] == "downloaded"
        assert stats["names"]["status"] == "downloaded"
        before = (out_dir / "stripped.gz").stat().st_mtime

        stats2 = sync_data(
            stripped_url=f"{base}/stripped.gz",
            names_url=f"{base}/names.gz",
            stripped_path=out_dir / "stripped.gz",
            names_path=out_dir / "names.gz",
            force=False,
        )
        assert stats2["stripped"]["status"] == "skipped"
        assert stats2["names"]["status"] == "skipped"
        assert (out_dir / "stripped.gz").stat().st_mtime == before


def test_sync_force_redownload(tmp_path: Path):
    src = tmp_path / "src_force"
    src.mkdir()
    (src / "stripped.gz").write_text("ORIGINAL", encoding="utf-8")
    (src / "names.gz").write_text("ORIGINALNAMES", encoding="utf-8")

    out_dir = tmp_path / "out_force"
    out_dir.mkdir()

    with serve_directory(src) as base:
        sync_data(
            stripped_url=f"{base}/stripped.gz",
            names_url=f"{base}/names.gz",
            stripped_path=out_dir / "stripped.gz",
            names_path=out_dir / "names.gz",
            force=False,
        )
        # Overwrite locally, then force re-download to restore contents
        (out_dir / "stripped.gz").write_text("MODIFIED", encoding="utf-8")
        stats = sync_data(
            stripped_url=f"{base}/stripped.gz",
            names_url=f"{base}/names.gz",
            stripped_path=out_dir / "stripped.gz",
            names_path=out_dir / "names.gz",
            force=True,
        )
        assert stats["stripped"]["status"] == "downloaded"
        assert (out_dir / "stripped.gz").read_text(encoding="utf-8") == "ORIGINAL"


def test_sync_clone_oeisdata_and_keywords(tmp_path: Path):
    # Create a tiny local git repo to stand in for oeisdata
    repo = tmp_path / "oeisdata_src"
    keywords_file = repo / "seq" / "KEYWORDS"
    keywords_file.parent.mkdir(parents=True)
    keywords_file.write_text("A900000 nonn,easy\n", encoding="utf-8")

    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    subprocess.run(["git", "add", "seq/KEYWORDS"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init keywords"], cwd=repo, check=True, stdout=subprocess.DEVNULL)

    clone_dir = tmp_path / "oeisdata_clone"
    stats = sync_data(
        stripped_url=None,
        names_url=None,
        stripped_path=tmp_path / "unused_stripped",
        names_path=tmp_path / "unused_names",
        clone_oeisdata=True,
        oeisdata_path=clone_dir,
        oeisdata_url=repo.as_posix(),
    )
    assert stats["oeisdata"]["status"] == "cloned"
    assert (clone_dir / "seq" / "KEYWORDS").exists()

    # Build index using keywords from cloned oeisdata mirror
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text("A900000 1,2,3\n", encoding="utf-8")
    names.write_text("A900000 Demo\n", encoding="utf-8")
    db = tmp_path / "oeis.db"
    build_index(stripped, names, None, db, oeisdata_root=clone_dir, max_terms=5)

    seqs = list(iter_sequences(db))
    assert seqs[0].keywords == ["nonn", "easy"]
