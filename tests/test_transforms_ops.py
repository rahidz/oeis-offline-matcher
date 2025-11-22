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
    mod_transform,
    xor_index_transform,
    run_length_encode_transform,
    run_length_decode_transform,
    mobius_transform,
    concat_index_value_transform,
    log_transform,
    exp_transform,
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
    shift_neg = make_shift(-2).apply([0, 1, 2, 3, 4])
    assert shift_neg == [0, 1, 2]


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
    ds2 = digit_sum_transform(2).apply([3, 4])
    assert ds2 == [2, 1]


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


def test_mod_and_xor_index_transforms():
    mod = mod_transform(5).apply([7, 11, -1])
    assert mod == [2, 1, 4]
    xor = xor_index_transform().apply([1, 2, 3])
    # 1^0=1, 2^1=3, 3^2=1
    assert xor == [1, 3, 1]


def test_run_length_encode_transform():
    rle = run_length_encode_transform().apply([1, 1, 2, 2, 2, 3])
    assert rle == [2, 3, 1]


def test_mobius_transform_basic():
    # a_n = n => Möbius transform gives phi(n)
    mob = mobius_transform().apply([1, 2, 3, 4, 5, 6])
    assert mob[:6] == [1, 1, 2, 2, 4, 2]
    # constant ones -> [1,0,0,...]
    mob2 = mobius_transform().apply([1, 1, 1, 1])
    assert mob2 == [1, 0, 0, 0]


def test_concat_index_value_transform():
    concat = concat_index_value_transform().apply([3, 5, 12])
    assert concat == [13, 25, 312]
    concat2 = concat_index_value_transform(2).apply([1, 1, 1])
    # base-2: indices 1,2,3 are "1","10","11" and a_n=1 => 11, 101, 111 (base2 -> 3,5,7 decimal)
    assert concat2 == [3, 5, 7]


def test_rle_decode_transform():
    rld = run_length_decode_transform().apply([2, 9, 1, 5])
    assert rld == [9, 9, 5]
    # odd length should give empty
    assert run_length_decode_transform().apply([1, 2, 3]) == []


def test_log_and_exp_transforms():
    log2 = log_transform(2.0).apply([1, 2, 4, 8])
    assert log2 == [0, 1, 2, 3]
    # exp base 2 with small exponents
    exp2 = exp_transform(2.0).apply([0, 1, 2, 3])
    assert exp2 == [1, 2, 4, 8]
    # log drops on nonpositive
    assert log_transform(2.0).apply([0, 1]) == []
    # exp drops on huge overflow
    assert exp_transform(2.0).apply([1000]) == []
