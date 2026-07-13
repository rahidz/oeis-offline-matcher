from pathlib import Path

from oeis_matcher.config import DEFAULT_CONFIG, load_config


def test_load_config_defaults(tmp_path: Path):
    cfg = load_config(tmp_path / "missing.toml")
    assert cfg["paths"]["stripped"] == DEFAULT_CONFIG["paths"]["stripped"]
    assert cfg["limits"]["max_terms"] == DEFAULT_CONFIG["limits"]["max_terms"]
    assert cfg["freshness"]["max_age_days"] == DEFAULT_CONFIG["freshness"]["max_age_days"]
    assert cfg["startup"]["show_status"] is DEFAULT_CONFIG["startup"]["show_status"]


def test_load_config_file(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
        [paths]
        db = "foo.db"
        [limits]
        max_results = 5
        [freshness]
        max_age_days = 14
        [startup]
        refresh_if_stale = true
        """,
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert cfg["paths"]["db"] == "foo.db"
    assert cfg["limits"]["max_results"] == 5
    assert cfg["freshness"]["max_age_days"] == 14
    assert cfg["startup"]["refresh_if_stale"] is True


def test_env_overrides(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OEIS_DB_PATH", "env.db")
    monkeypatch.setenv("OEIS_MAX_TERMS", "256")
    monkeypatch.setenv("OEIS_FRESHNESS_MAX_AGE_DAYS", "45")
    monkeypatch.setenv("OEIS_WARN_ON_STALE_DATA", "false")
    monkeypatch.setenv("OEIS_STARTUP_REFRESH_IF_STALE", "1")
    cfg = load_config(tmp_path / "missing.toml")
    assert cfg["paths"]["db"] == "env.db"
    assert cfg["limits"]["max_terms"] == 256
    assert cfg["freshness"]["max_age_days"] == 45
    assert cfg["freshness"]["warn_on_stale"] is False
    assert cfg["startup"]["refresh_if_stale"] is True
