from __future__ import annotations

from oeis_matcher.cli import PRESETS


def test_runtime_contracts_for_fast_deep_max_presets():
    assert set(PRESETS.keys()) == {"fast", "deep", "max"}

    fast = PRESETS["fast"]
    deep = PRESETS["deep"]
    maxp = PRESETS["max"]

    assert fast["total_max_time"] <= 10.0
    assert 60.0 <= deep["total_max_time"] <= 180.0
    assert maxp["total_max_time"] >= 1800.0
    assert fast["total_max_time"] < deep["total_max_time"] < maxp["total_max_time"]

    for preset in (fast, deep, maxp):
        assert preset["transform_max_time"] <= preset["total_max_time"]
        assert preset["combo_max_time"] <= preset["total_max_time"]
        assert preset["max_time"] <= preset["total_max_time"]
        assert preset["exact_max_time"] <= preset["total_max_time"]
        assert preset["similarity_max_time"] <= preset["total_max_time"]
        assert preset["candidate_max_time"] <= preset["total_max_time"]
        assert preset["combo_candidate_max_time"] <= preset["total_max_time"]


def test_max_preset_is_exhaustive_ceiling_defaults():
    maxp = PRESETS["max"]
    assert maxp["stream"] is True
    assert maxp["expanded"] is True
    assert maxp["combo_expanded"] is True
    assert maxp["candidates"] > PRESETS["deep"]["candidates"]
    assert maxp["combo_max_checks"] > PRESETS["deep"]["combo_max_checks"]
