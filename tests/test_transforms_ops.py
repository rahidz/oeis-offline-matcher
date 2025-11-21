from oeis_matcher.transforms import (
    abs_transform,
    diff_transform,
    diff_k_transform,
    gcd_normalize_transform,
    make_shift,
    partial_sum_transform,
    decimate_transform,
    cumulative_product_transform,
    popcount_transform,
    digit_sum_transform,
    reverse_transform,
    even_terms_transform,
    odd_terms_transform,
    moving_sum_transform,
)


def test_diff_transform():
    diff = diff_transform().apply([1, 3, 6, 10])
    assert diff == [2, 3, 4]


def test_diff_k_transform():
    diff2 = diff_k_transform(2).apply([1, 3, 6, 10])
    assert diff2 == [1, 1]


def test_partial_sum_transform():
    ps = partial_sum_transform().apply([1, 2, 3])
    assert ps == [1, 3, 6]


def test_shift_transform():
    shift2 = make_shift(2).apply([0, 1, 2, 3, 4])
    assert shift2 == [2, 3, 4]


def test_abs_transform():
    result = abs_transform().apply([-1, 0, 5, -7])
    assert result == [1, 0, 5, 7]


def test_gcd_normalize_transform():
    norm = gcd_normalize_transform().apply([2, 4, 6])
    assert norm == [1, 2, 3]


def test_decimate_transform():
    dec = decimate_transform(2, 0).apply([1, 2, 3, 4, 5])
    assert dec == [1, 3, 5]


def test_cumulative_product_transform():
    cp = cumulative_product_transform().apply([1, 2, 3, 4])
    assert cp == [1, 2, 6, 24]


def test_popcount_transform():
    pc = popcount_transform().apply([1, 2, 3, 7])
    assert pc == [1, 1, 2, 3]


def test_digit_sum_transform():
    ds = digit_sum_transform().apply([0, 12, -305])
    assert ds == [0, 3, 8]


def test_reverse_transform():
    rev = reverse_transform().apply([1, 2, 3])
    assert rev == [3, 2, 1]


def test_even_odd_transforms():
    even = even_terms_transform().apply([1, 2, 3, 4, 5])
    odd = odd_terms_transform().apply([1, 2, 3, 4, 5])
    assert even == [1, 3, 5]
    assert odd == [2, 4]


def test_moving_sum_transform():
    mv = moving_sum_transform(2).apply([1, 2, 3, 4])
    assert mv == [3, 5, 7]
