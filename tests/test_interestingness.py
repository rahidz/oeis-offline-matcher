import math
import random
from fractions import Fraction

from oeis_matcher import interestingness
from oeis_matcher.interestingness import score_sequence


def fibonacci(count=30):
    terms = [0, 1]
    while len(terms) < count:
        terms.append(sum(terms[-2:]))
    return terms


def test_validated_recurrence_beats_noise_and_trivial_growth():
    fib = score_sequence({"terms": fibonacci()})
    rng = random.Random(17)
    noise = score_sequence({"terms": [rng.randrange(10000) for _ in range(30)]})
    geometric = score_sequence({"terms": [2**i for i in range(30)]})
    assert fib["discovery"] > geometric["discovery"] > noise["discovery"]
    assert noise["discovery"] == 0
    structure = fib["evidence"]["structure"]
    assert structure["validated"]
    assert structure["model"] == "linear recurrence order 2"
    assert structure["parameters"] == ["1", "1", "0", "1"]
    assert structure["holdout_passed"] == structure["holdout_terms"] == 10


def test_holdout_is_not_used_for_fitting():
    clean = fibonacci()
    changed = clean[:]
    changed[20] += 1
    a = score_sequence({"terms": clean})["evidence"]["structure"]
    b = score_sequence({"terms": changed})["evidence"]["structure"]
    assert a["train_terms"] == b["train_terms"] == 20
    assert a["parameters"] == b["parameters"]
    assert a["validated"] and not b["validated"]
    assert b["status"] == "held-out prediction failed"
    assert b["savings"] == 0


def test_polynomial_and_factorial_models():
    for terms, name in (([n**3 for n in range(30)], "polynomial degree 3"),
                        ([math.factorial(n) for n in range(25)], "affine term ratio")):
        evidence = score_sequence({"terms": terms})["evidence"]["structure"]
        assert evidence["validated"]
        assert evidence["model"] == name
        assert evidence["description_bits"] < evidence["literal_bits"]


def test_short_sequence_does_not_claim_prediction():
    result = score_sequence({"terms": [1, 1, 2, 3]})
    assert result["discovery"] == 0
    assert result["evidence"]["structure"]["status"] == "insufficient terms"
    assert result["evidence"]["novelty"]["corpus_novelty"] == "unknown"


def test_notability_is_distinct_and_balanced_is_mean():
    record = {"terms": fibonacci(), "keywords": ["core", "nice"], "inbound_links": 1000,
              "references": "\n".join(["A reference"] * 15), "links": "\n".join(["A link"] * 15)}
    result = score_sequence(record)
    assert result["notability"] == 100
    assert result["balanced"] == round((100 + result["discovery"]) / 2, 2)
    assert all(result["evidence"]["notability"]["coverage"].values())
    sparse = score_sequence({"terms": fibonacci(), "references": "", "inbound_links": 0})
    coverage = sparse["evidence"]["notability"]["coverage"]
    assert coverage["references"] and coverage["inbound_links"]
    assert not coverage["links"]
    assert sparse["discovery"] == result["discovery"]


def test_domain_hints_are_not_counted_as_proven_independence():
    result = score_sequence({"terms": [], "name": "Prime partitions of lattice graphs"})
    assert len(result["evidence"]["connections"]["families"]) == 3
    assert "not proven" in result["evidence"]["connections"]["status"]
    assert result["evidence"]["novelty"]["corpus_novelty"] == "unknown"


def test_probe_limits_and_determinism():
    terms = fibonacci(60)
    result = score_sequence({"terms": terms})
    assert result == score_sequence({"terms": terms[:48] + [123456789] * 20})
    assert result == score_sequence({"terms": terms})
    large = score_sequence({"terms": [2**5000 + i for i in range(30)]})
    assert large["discovery"] == 0
    assert "4096-bit" in large["evidence"]["structure"]["status"]


def test_all_zero_and_signed_terms():
    for terms in ([0] * 20, [(-1)**n * n**2 for n in range(30)]):
        result = score_sequence({"terms": terms})
        assert 0 <= result["discovery"] <= 100
        assert result["evidence"]["structure"]["validated"]


def test_model_selection_does_not_consult_holdout(monkeypatch):
    terms = fibonacci()

    def models(train, count):
        assert train == terms[:20]
        yield "cheap failure", [1], train + [0] * (count - len(train)), False
        yield "expensive success", [123456], terms, False

    monkeypatch.setattr(interestingness, "_models", models)
    result = score_sequence({"terms": terms})
    assert result["discovery"] == 0
    assert result["evidence"]["structure"]["model"] == "cheap failure"
    assert not result["evidence"]["structure"]["validated"]


def test_reported_recurrence_parameters_replay_independently():
    terms = [1, 3, -2]
    while len(terms) < 36:
        terms.append(2 * terms[-1] - terms[-2] + 3 * terms[-3])
    evidence = score_sequence({"terms": terms})["evidence"]["structure"]
    assert evidence["model"] == "linear recurrence order 3"
    parameters = [Fraction(value) for value in evidence["parameters"]]
    coefficients, initial = parameters[:3], parameters[3:]
    assert coefficients == [2, -1, 3]
    assert initial == terms[:3]
    # Replay from only the declared parameters and seeds, without using the
    # scorer's recurrence implementation or any observed intermediate values.
    replay = initial[:]
    for n in range(3, len(terms)):
        replay.append(sum(coefficients[i] * replay[n - i - 1] for i in range(3)))
    assert replay == terms
    assert evidence["holdout_passed"] == 12


def test_rational_parameter_cost_includes_unit_denominator():
    evidence = score_sequence({"terms": fibonacci()})["evidence"]["structure"]
    # Family tag 8, two rational coefficients 1/1 costing 8 each, seeds
    # 0 and 1 costing 2 and 4. Calculate without the internal cost helper.
    assert evidence["description_bits"] == 8 + 2 * (4 + 4) + 2 + 4


def test_affine_prefix_crowding_discounts_only_validated_nontrivial_structure():
    record = {"terms": fibonacci(), "name": "Prime partitions of lattice graphs"}
    plain = score_sequence(record)
    uncrowded = score_sequence({**record, "affine_prefix_relatives": 0, "affine_prefix_terms": 16})
    crowded = score_sequence({**record, "affine_prefix_relatives": 255, "affine_prefix_terms": 16})
    assert plain["discovery"] == uncrowded["discovery"]
    assert crowded["discovery"] < plain["discovery"]
    # Three domains contribute 20*2/3, outside the structure-only multiplier.
    hints = 20 * 2 / 3
    assert abs(crowded["discovery"] - ((plain["discovery"] - hints) / 1.5 + hints)) < .02
    novelty = crowded["evidence"]["novelty"]
    assert novelty["corpus_novelty"] == "unknown"
    assert novelty["affine_prefix_relatives"] == 255
    assert "stored prefixes" in novelty["status"]


def test_affine_prefix_crowding_does_not_reward_noise_or_discount_trivial_models():
    rng = random.Random(42)
    for terms in ([rng.randrange(100000) for _ in range(30)], [2**n for n in range(30)]):
        plain = score_sequence({"terms": terms})
        crowded = score_sequence({"terms": terms, "affine_prefix_relatives": 1000, "affine_prefix_terms": 16})
        assert plain["discovery"] == crowded["discovery"]
        assert crowded["evidence"]["novelty"]["crowding_weight"] == 1


def test_affine_prefix_crowding_requires_declared_sixteen_term_window():
    plain = score_sequence({"terms": fibonacci()})
    short = score_sequence({"terms": fibonacci(), "affine_prefix_relatives": 100, "affine_prefix_terms": 5})
    assert plain["discovery"] == short["discovery"]
