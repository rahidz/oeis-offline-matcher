from oeis_matcher.cli import _parse_extra_transforms


def test_parse_extra_transforms_supports_new_families():
    extras = _parse_extra_transforms(
        "altsign,invbinomial,eulerogf,inveulerogf,stirling1,stirling2,invstirling1,invstirling2,ogfinv,seriesrev,vp3,vp5,lpf,gpf,rad,squarefree,liouville,ratioint,indextri,indexfib,indexpowk3"
    )

    assert extras["alt_sign"] is True
    assert extras["inv_binomial"] is True
    assert extras["euler_ogf"] is True
    assert extras["inv_euler_ogf"] is True
    assert extras["stirling1"] is True
    assert extras["stirling2"] is True
    assert extras["inv_stirling1"] is True
    assert extras["inv_stirling2"] is True
    assert extras["ogf_inverse"] is True
    assert extras["series_reversion"] is True
    assert extras["vp_values"] == (3, 5)
    assert extras["lpf"] is True
    assert extras["gpf"] is True
    assert extras["rad"] is True
    assert extras["squarefree"] is True
    assert extras["liouville"] is True
    assert extras["ratio_int"] is True
    assert extras["index_triangular"] is True
    assert extras["index_fibonacci"] is True
    assert extras["index_power_values"] == (3,)
