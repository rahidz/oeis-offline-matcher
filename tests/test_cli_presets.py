from types import SimpleNamespace

from oeis_matcher.cli import _apply_preset, PRESETS


def test_max_preset_applies_key_fields():
    args = SimpleNamespace(
        max_depth=1,
        limit=5,
        tlimit=5,
        combos=0,
        triples=0,
        combo_max_time=None,
        triple_max_time=None,
    )
    updated = _apply_preset(args, "max")
    preset = PRESETS["max"]
    assert updated.max_depth == preset["max_depth"]
    assert updated.tlimit == preset["tlimit"]
    assert updated.combos == preset["combos"]
    assert updated.triples == preset["triples"]
    assert updated.combo_max_time == preset["combo_max_time"]
    assert updated.triple_max_time == preset["triple_max_time"]
