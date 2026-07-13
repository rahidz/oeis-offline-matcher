from pathlib import Path
import tomllib

from oeis_matcher import __version__


def test_package_version_matches_project_metadata():
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["version"] == __version__
