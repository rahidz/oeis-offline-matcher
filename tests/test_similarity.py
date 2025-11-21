from oeis_matcher.similarity import correlation, mse_after_scale_offset


def test_correlation_basic():
    assert abs(correlation([1, 2, 3], [2, 4, 6]) - 1.0) < 1e-9
    assert correlation([1, 1, 1], [2, 3, 4]) == 0.0


def test_mse_scale_offset():
    mse, a, b = mse_after_scale_offset([2, 4, 6], [1, 2, 3])
    assert abs(a - 2.0) < 1e-9
    assert abs(b) < 1e-9
    assert mse < 1e-9
