from fractions import Fraction

from oeis_matcher.pattern_probe import normalize_by_m_pow_cm, split_by_mod_class, try_fit_affine, valuations_2_5


def test_split_by_mod_class_n0_1():
    terms = [10, 11, 12, 13, 14]  # a(1)..a(5)
    slices = split_by_mod_class(terms, 2, n0=1)
    assert slices[1].ns == [1, 3, 5]
    assert slices[1].terms == [10, 12, 14]
    assert slices[0].ns == [2, 4]
    assert slices[0].terms == [11, 13]


def test_valuations_2_5():
    a = 2 * (5**10)
    b = 29 * (5**9)
    rows = valuations_2_5([a, b], n0=20)
    assert rows[0].n == 20
    assert rows[0].v2 == 1
    assert rows[0].v5 == 10
    assert rows[0].rest_2_5 == 1
    assert rows[1].n == 21
    assert rows[1].v2 == 0
    assert rows[1].v5 == 9
    assert rows[1].rest_2_5 == 29


def test_normalize_by_m_pow_cm_hits_constant_for_mod4_r0():
    # A003432 terms up to n=20
    terms = [
        1,
        1,
        1,
        2,
        3,
        5,
        9,
        32,
        56,
        144,
        320,
        1458,
        3645,
        9477,
        25515,
        131072,
        327680,
        1114112,
        3411968,
        19531250,
    ]
    slices = split_by_mod_class(terms, 4, n0=1)
    r0 = slices[0]
    norm = normalize_by_m_pow_cm(r0, exp_coeff=2, require_m_positive=True)
    assert norm.m_values == [1, 2, 3, 4, 5]
    assert norm.ratios == [Fraction(2, 1)] * 5


def test_try_fit_affine_exact():
    fit = try_fit_affine([1, 2, 3, 4], [5, 9, 13, 17])
    assert fit == (Fraction(4, 1), Fraction(1, 1))

