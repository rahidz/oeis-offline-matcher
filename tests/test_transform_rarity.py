from oeis_matcher.transform_search import _invariant_rarity_bonus


def test_invariant_rarity_bonus_prefers_rare_patterns():
    stats = {
        "total": 100,
        "sign_pattern": {"nonneg": 90, "alternating": 10},
        "first_diff_sign": {"mixed": 100},
    }
    common = _invariant_rarity_bonus([1, 2, 3, 4], stats)
    rare = _invariant_rarity_bonus([1, -1, 1, -1], stats)
    assert rare > common


def test_invariant_rarity_bonus_handles_missing_stats():
    assert _invariant_rarity_bonus([1, 2, 3], {}) == 0.0
    assert _invariant_rarity_bonus([], {"total": 10}) == 0.0
