from __future__ import annotations

from oeis_matcher.explanation_ranking import rerank_explanations
from oeis_matcher.models import CombinationMatch, Match


def _tm(score: float, desc: str, *, sid: str = "A000045") -> Match:
    return Match(
        id=sid,
        name=None,
        match_type="prefix",
        offset=0,
        length=6,
        score=score,
        transform_desc=desc,
    )


def _cm(score: float, expr: str, *, ids: tuple[str, str] = ("A000027", "A000012")) -> CombinationMatch:
    return CombinationMatch(
        ids=ids,
        names=(None, None),
        coeffs=(1, 1),
        shifts=(0, 0),
        length=6,
        score=score,
        expression=expr,
    )


def test_rerank_uses_family_quota_before_global_fill():
    transforms = [
        _tm(100.0, "shift(1)"),
        _tm(99.0, "shift(2)"),
        _tm(98.0, "diff"),
    ]
    pointwise = [
        _cm(50.0, "a(n) = gcd(A000027(n), A000012(n))"),
    ]

    ranked, diag = rerank_explanations(
        transform_matches=transforms,
        family_matches={"pointwise": pointwise},
        limit=2,
        default_quota=1,
        diversity=True,
    )

    assert len(ranked) == 2
    assert {fam for fam, _ in ranked} == {"transform", "pointwise"}
    assert diag["selected_counts"]["transform"] == 1
    assert diag["selected_counts"]["pointwise"] == 1


def test_rerank_diversity_dedup_suppresses_near_duplicate_transforms():
    transforms = [
        _tm(100.0, "shift(1)"),
        _tm(99.5, "shift(2)"),  # near-duplicate family on same id
        _tm(90.0, "diff"),
    ]

    ranked_diverse, diag_diverse = rerank_explanations(
        transform_matches=transforms,
        family_matches={},
        limit=3,
        default_quota=0,
        diversity=True,
    )
    ranked_plain, _diag_plain = rerank_explanations(
        transform_matches=transforms,
        family_matches={},
        limit=3,
        default_quota=0,
        diversity=False,
    )

    assert len(ranked_diverse) == 2
    assert len(ranked_plain) == 3
    assert diag_diverse["dedupe_dropped"] >= 1
