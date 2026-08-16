import subprocess
import urllib.request
from io import BytesIO
from pathlib import Path

import pytest

from oeis_matcher.build_index import build_index
from oeis_matcher.storage import iter_sequences
from oeis_matcher.sync import clone_oeisdata_repo, download_file, sync_data


def test_sync_downloads_and_skips_existing(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "stripped.gz").write_text("SAMPLE_STRIPPED", encoding="utf-8")
    (src / "names.gz").write_text("SAMPLE_NAMES", encoding="utf-8")

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    stripped_src = (src / "stripped.gz").as_uri()
    names_src = (src / "names.gz").as_uri()

    stats = sync_data(
        stripped_url=stripped_src,
        names_url=names_src,
        stripped_path=out_dir / "stripped.gz",
        names_path=out_dir / "names.gz",
        force=False,
    )
    assert stats["stripped"]["status"] == "downloaded"
    assert stats["names"]["status"] == "downloaded"
    before = (out_dir / "stripped.gz").stat().st_mtime

    stats2 = sync_data(
        stripped_url=stripped_src,
        names_url=names_src,
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

    stripped_src = (src / "stripped.gz").as_uri()
    names_src = (src / "names.gz").as_uri()

    sync_data(
        stripped_url=stripped_src,
        names_url=names_src,
        stripped_path=out_dir / "stripped.gz",
        names_path=out_dir / "names.gz",
        force=False,
    )
    # Overwrite locally, then force re-download to restore contents
    (out_dir / "stripped.gz").write_text("MODIFIED", encoding="utf-8")
    stats = sync_data(
        stripped_url=stripped_src,
        names_url=names_src,
        stripped_path=out_dir / "stripped.gz",
        names_path=out_dir / "names.gz",
        force=True,
    )
    assert stats["stripped"]["status"] == "downloaded"
    assert (out_dir / "stripped.gz").read_text(encoding="utf-8") == "ORIGINAL"


def test_remote_download_identifies_the_client(tmp_path: Path, monkeypatch):
    seen = []

    def respond(request):
        seen.append(request)
        return BytesIO(b"snapshot")

    monkeypatch.setattr(urllib.request, "urlopen", respond)
    dest = tmp_path / "snapshot.gz"
    download_file("https://oeis.org/stripped.gz", dest)

    assert dest.read_bytes() == b"snapshot"
    assert seen[0].full_url == "https://oeis.org/stripped.gz"
    assert seen[0].get_header("User-agent").startswith("oeis-offline-matcher/")


def test_failed_force_download_preserves_existing_snapshot(tmp_path: Path, monkeypatch):
    dest = tmp_path / "snapshot.gz"
    dest.write_bytes(b"known-good")

    def fail(_url):
        raise OSError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    try:
        download_file("https://example.invalid/snapshot.gz", dest, force=True)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected the simulated download to fail")

    assert dest.read_bytes() == b"known-good"
    assert not dest.with_suffix(".gz.tmp").exists()


def test_failed_clone_leaves_no_partial_destination(tmp_path: Path, monkeypatch):
    dest = tmp_path / "oeisdata"

    def fail(command, **_kwargs):
        partial = Path(command[-1])
        partial.mkdir()
        (partial / "partial").write_text("incomplete", encoding="utf-8")
        return subprocess.CompletedProcess(command, 1, stderr="clone failed")

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(RuntimeError, match="clone failed"):
        clone_oeisdata_repo(dest)

    assert not dest.exists()
    assert not list(tmp_path.glob(".oeisdata.clone-*"))


def test_cancelled_force_clone_preserves_existing_destination(tmp_path: Path, monkeypatch):
    dest = tmp_path / "oeisdata"
    dest.mkdir()
    (dest / "snapshot").write_text("known-good", encoding="utf-8")

    def cancel(command, **_kwargs):
        partial = Path(command[-1])
        partial.mkdir()
        (partial / "partial").write_text("incomplete", encoding="utf-8")
        raise KeyboardInterrupt

    monkeypatch.setattr(subprocess, "run", cancel)
    with pytest.raises(KeyboardInterrupt):
        clone_oeisdata_repo(dest, force=True)

    assert (dest / "snapshot").read_text(encoding="utf-8") == "known-good"
    assert not list(tmp_path.glob(".oeisdata.clone-*"))


def test_force_clone_replaces_only_after_clone_succeeds(tmp_path: Path, monkeypatch):
    dest = tmp_path / "oeisdata"
    dest.mkdir()
    (dest / "snapshot").write_text("old", encoding="utf-8")

    def succeed(command, **_kwargs):
        assert (dest / "snapshot").read_text(encoding="utf-8") == "old"
        clone = Path(command[-1])
        clone.mkdir()
        (clone / "snapshot").write_text("new", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stderr="")

    monkeypatch.setattr(subprocess, "run", succeed)
    stats = clone_oeisdata_repo(dest, force=True)

    assert stats["status"] == "cloned"
    assert (dest / "snapshot").read_text(encoding="utf-8") == "new"
    assert not list(tmp_path.glob(".oeisdata.clone-*"))


def test_clone_recovers_destination_from_interrupted_publish(tmp_path: Path, monkeypatch):
    dest = tmp_path / "oeisdata"
    backup = tmp_path / ".oeisdata.clone-tmp" / "previous"
    backup.mkdir(parents=True)
    (backup / "snapshot").write_text("known-good", encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: pytest.fail("clone should be skipped"))

    stats = clone_oeisdata_repo(dest)

    assert stats["status"] == "skipped"
    assert (dest / "snapshot").read_text(encoding="utf-8") == "known-good"
    assert not (tmp_path / ".oeisdata.clone-tmp").exists()


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
