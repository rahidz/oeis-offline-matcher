from math import comb

from oeis_matcher.quasipolynomial import detect_quasipolynomial


def test_polynomial_uses_smallest_period_and_exact_coefficients():
    terms = [2**100 - comb(n, 2) for n in range(21)]
    result = detect_quasipolynomial(terms)
    assert result is not None
    assert result["period"] == 1
    assert result["index_origin"] == 0
    assert result["constituents"][0]["coefficients"] == [2**100, 0, -1]
    assert result["constituents"][0]["formula"] == f"{2**100} - binom(m, 2)"
    assert result["validation"] == {
        "fit_terms": 3,
        "holdout_terms": 18,
        "min_holdout_terms_per_class": 18,
    }


def test_odd_even_quasipolynomial():
    result = detect_quasipolynomial([n * n // 4 for n in range(21)])
    assert result is not None
    assert result["period"] == 2
    even, odd = result["constituents"]
    assert (even["residue"], even["coefficients"]) == (0, [0, 1, 2])
    assert (odd["residue"], odd["coefficients"]) == (1, [0, 2, 2])
    assert "a(2m) = m^2" in result["formula"]
    assert "a(2m + 1) = m^2 + m" in result["formula"]


def test_mixed_degrees_with_custom_index_origin():
    origin = -4
    terms = [(17, -((n + 2) // 3), 7 + comb((n + 4) // 3, 3))[n % 3] for n in range(origin, 21)]
    result = detect_quasipolynomial(terms, index_origin=origin)
    assert result is not None
    assert result["period"] == 3
    assert result["index_origin"] == origin
    assert [(c["first_index"], c["degree"]) for c in result["constituents"]] == [(-3, 0), (-2, 1), (-4, 3)]
    for constituent in result["constituents"]:
        values = terms[constituent["first_index"] - origin :: 3]
        coefficients = constituent["coefficients"]
        assert [sum(c * comb(m, k) for k, c in enumerate(coefficients)) for m in range(len(values))] == values
        assert constituent["fit_terms"] == len(coefficients)
        assert constituent["holdout_terms"] == len(values) - len(coefficients)
    assert result["validation"]["min_holdout_terms_per_class"] == 5


def test_requires_two_holdouts_in_every_class_and_checks_the_tail():
    terms = [100 + (n // 2) ** 2 if n % 2 else 0 for n in range(30)]
    assert detect_quasipolynomial(terms[:9]) is None
    assert detect_quasipolynomial(terms[:10])["period"] == 2
    assert detect_quasipolynomial(terms[:-1] + [terms[-1] + 1]) is None


def test_rejects_wildcards_and_models_outside_search_bounds():
    assert detect_quasipolynomial([0, 1, None, 3, 4, 5, 6, 7]) is None
    assert detect_quasipolynomial([n**4 for n in range(80)]) is None
    assert detect_quasipolynomial([n % 9 for n in range(80)]) is None


def test_can_cancel_during_holdout_checks():
    checks = 0

    def should_stop():
        nonlocal checks
        checks += 1
        return checks >= 6  # Four wildcard-scan checks, then fit and first holdout batch.

    assert detect_quasipolynomial([1] * 1024, should_stop=should_stop) is None
