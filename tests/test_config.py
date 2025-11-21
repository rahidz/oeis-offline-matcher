from pathlib import Path
import os

from oeis_matcher.config import DEFAULT_CONFIG, load_config


def test_load_config_defaults(tmp_path: Path):
    cfg = load_config(tmp_path / "missing.toml")
    assert cfg["paths"]["stripped"] == DEFAULT_CONFIG["paths"]["stripped"]
    assert cfg["limits"]["max_terms"] == DEFAULT_CONFIG["limits"]["max_terms"]


def test_load_config_file(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
        [paths]
        db = "foo.db"
        [limits]
        max_results = 5
        """,
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert cfg["paths"]["db"] == "foo.db"
    assert cfg["limits"]["max_results"] == 5


def test_env_overrides(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OEIS_DB_PATH", "env.db")
    monkeypatch.setenv("OEIS_MAX_TERMS", "256")
    cfg = load_config(tmp_path / "missing.toml")
    assert cfg["paths"]["db"] == "env.db"
    assert cfg["limits"]["max_terms"] == 256
