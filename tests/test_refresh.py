import gzip
import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from oeis_matcher import refresh as refresh_module
from oeis_matcher.build_index import build_index
from oeis_matcher.config import DEFAULT_CONFIG
from oeis_matcher.storage import iter_sequences


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _commit(repo: Path):
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "update fixture")


@pytest.fixture
def refresh_workspace(tmp_path: Path):
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-qb", "main")
    _git(origin, "config", "user.name", "Test User")
    _git(origin, "config", "user.email", "test@example.com")
    seq = origin / "seq" / "A700"
    seq.mkdir(parents=True)
    (seq / "A700000.seq").write_text(
        "%K A700000 nonn,easy\n%O A700000 0,1\n%F A700000 Old formula.\n",
        encoding="utf-8",
    )
    support = origin / "files" / "A700" / "b700000.txt"
    support.parent.mkdir(parents=True)
    support.write_text("0 1\n", encoding="utf-8")
    _commit(origin)
    repo = tmp_path / "mirror"
    subprocess.run(["git", "clone", "--quiet", origin.as_uri(), str(repo)], check=True)
    (repo / "files" / "A700" / "b700000.txt").write_text("0 999\n", encoding="utf-8")

    (seq / "A700000.seq").write_text(
        "%K A700000 nonn,more\n%O A700000 1,2\n%F A700000 a(n) = 10*n.\n",
        encoding="utf-8",
    )
    (seq / "A700001.seq").write_text(
        "%K A700001 nonn,easy\n%O A700001 1,1\n%F A700001 a(n) = n^2.\n",
        encoding="utf-8",
    )
    _commit(origin)

    raw = tmp_path / "raw"
    raw.mkdir()
    cfg = deepcopy(DEFAULT_CONFIG)
    cfg["paths"] = {
        "stripped": str(raw / "stripped.gz"), "names": str(raw / "names.gz"),
        "keywords": str(raw / "keywords.txt"), "db": str(tmp_path / "oeis.db"),
    }
    cfg["freshness"]["metadata_path"] = str(tmp_path / "freshness.json")
    with gzip.open(raw / "stripped.gz", "wt") as output:
        output.write("A700000 1,2,3\n")
    with gzip.open(raw / "names.gz", "wt") as output:
        output.write("A700000 Old sequence\n")
    (raw / "keywords.txt").write_text("A700000 nonn,easy\n", encoding="utf-8")
    build_index(raw / "stripped.gz", raw / "names.gz", raw / "keywords.txt", Path(cfg["paths"]["db"]))

    sources = tmp_path / "sources"
    sources.mkdir()
    with gzip.open(sources / "stripped.gz", "wt") as output:
        output.write("A700000 10,20,30\nA700001 1,4,9\n")
    with gzip.open(sources / "names.gz", "wt") as output:
        output.write("A700000 Multiples of ten\nA700001 Squares\n")
    return cfg, origin, repo, sources


def test_refresh_updates_all_metadata_and_preserves_unrelated_repairs(refresh_workspace):
    cfg, origin, repo, sources = refresh_workspace
    stats = refresh_module.refresh(
        cfg, repo=repo, stripped_url=(sources / "stripped.gz").as_uri(),
        names_url=(sources / "names.gz").as_uri(), skip_bfiles=True,
    )
    assert stats["inserted"] == 2
    first, second = list(iter_sequences(Path(cfg["paths"]["db"])))
    assert first.terms == [10, 20, 30]
    assert first.name == "Multiples of ten"
    assert first.keywords == ["nonn", "more"]
    assert first.offset == (1, 2)
    assert first.formula == "a(n) = 10*n."
    assert second.keywords == ["nonn", "easy"]
    assert second.offset == (1, 1)
    assert second.formula == "a(n) = n^2."
    raw = Path(cfg["paths"]["stripped"]).parent
    assert (raw / "keywords.txt").read_text() == "A700000 nonn,more\nA700001 nonn,easy\n"
    assert (raw / "offsets.txt").read_text() == "A700000 1,2\nA700001 1,1\n"
    assert (raw / "formulas.txt").read_text() == "A700000 a(n) = 10*n.\nA700001 a(n) = n^2.\n"
    assert (raw / "stripped.gz").read_bytes() == (sources / "stripped.gz").read_bytes()
    assert (raw / "names.gz").read_bytes() == (sources / "names.gz").read_bytes()
    metadata = json.loads(Path(cfg["freshness"]["metadata_path"]).read_text())
    assert metadata["last_sync_utc"] and metadata["last_build_utc"]
    assert metadata["sync"]["content_updated"]
    assert metadata["build"]["results"]["inserted"] == 2
    assert _git(repo, "rev-parse", "HEAD") == _git(origin, "rev-parse", "HEAD")
    assert _git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"
    assert (repo / "files" / "A700" / "b700000.txt").read_text() == "0 999\n"


@pytest.mark.parametrize("failure", ["missing-keywords", "download"])
def test_failed_refresh_preserves_database_and_raw_exports(refresh_workspace, monkeypatch, failure):
    cfg, origin, repo, sources = refresh_workspace
    if failure == "missing-keywords":
        (origin / "seq" / "A700" / "A700001.seq").write_text("%O A700001 1,1\n", encoding="utf-8")
        _commit(origin)
    names_url = (sources / ("absent.gz" if failure == "download" else "names.gz")).as_uri()
    before = {Path(value): Path(value).read_bytes() for value in cfg["paths"].values()}

    def unexpected_build(*args, **kwargs):
        pytest.fail("refresh must validate/download before building")

    monkeypatch.setattr(refresh_module, "build_index", unexpected_build)
    expected = "Inconsistent exports" if failure == "missing-keywords" else "Failed to download"
    with pytest.raises(RuntimeError, match=expected):
        refresh_module.refresh(
            cfg, repo=repo, stripped_url=(sources / "stripped.gz").as_uri(),
            names_url=names_url, skip_bfiles=True,
        )
    for path, content in before.items():
        assert path.read_bytes() == content
    assert not Path(cfg["freshness"]["metadata_path"]).exists()
    assert not list(Path(cfg["paths"]["stripped"]).parent.glob(".refresh-*"))


@pytest.mark.parametrize("direct_fails", [False, True])
def test_refresh_bfiles_uses_targeted_lfs_then_direct_fallback(tmp_path: Path, monkeypatch, direct_fails):
    files = tmp_path / "files" / "A700"
    files.mkdir(parents=True)
    for seq_id in ("700000", "700001"):
        (files / f"b{seq_id}.txt").write_text("version https://git-lfs.github.com/spec/v1\n", encoding="utf-8")
    (files / "b700002.txt").write_text("0 1\n", encoding="utf-8")
    (files / "b700003_1.txt").write_text("version https://git-lfs.github.com/spec/v1\n", encoding="utf-8")
    commands = []
    downloaded = []

    def run(command, **kwargs):
        commands.append(command)
        if "checkout" in command:
            (files / "b700000.txt").write_text("0 1\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 1 if "fetch" in command else 0)

    def fetch(ids, *, dest_root):
        assert dest_root == tmp_path / "files"
        downloaded.extend(ids)
        if not direct_fails:
            (files / "b700001.txt").write_text("0 2\n", encoding="utf-8")
        return {
            "failed": int(direct_fails),
            "files": [{"id": ids[0], "status": "failed" if direct_fails else "downloaded"}],
        }

    monkeypatch.setattr(refresh_module.subprocess, "run", run)
    monkeypatch.setattr(refresh_module, "fetch_bfiles", fetch)
    if direct_fails:
        with pytest.raises(RuntimeError, match="1 canonical b-files still unavailable: A700001"):
            refresh_module.refresh_bfiles(tmp_path)
    else:
        assert refresh_module.refresh_bfiles(tmp_path) == {"updated": 2}
    assert downloaded == ["A700001"]
    assert len(commands) == 2
    include = next(arg for arg in commands[0] if arg.startswith("--include="))
    assert set(include.removeprefix("--include=").split(",")) == {
        "files/A700/b700000.txt", "files/A700/b700001.txt",
    }
    assert commands[0][-2:] == ["origin", "HEAD"]
