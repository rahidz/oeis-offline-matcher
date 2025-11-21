from pathlib import Path

from oeis_matcher.build_index import build_index
from oeis_matcher.query import parse_query
from oeis_matcher.transform_search import search_transform_matches
from oeis_matcher.transforms import default_transforms


def _make_sample_raw(tmp_path: Path):
    stripped = tmp_path / "stripped.txt"
    names = tmp_path / "names.txt"
    stripped.write_text(
        "\n".join(
            [
                "A100000 2,4,6,8,10",
                "A100001 1,2,3,4,5",
            ]
        ),
        encoding="utf-8",
    )
    names.write_text(
        "\n".join(
            [
                "A100000 Twice the naturals",
                "A100001 Naturals",
            ]
        ),
        encoding="utf-8",
    )
    return stripped, names


def test_transform_scale_hits_scaled_sequence(tmp_path: Path):
    stripped, names = _make_sample_raw(tmp_path)
    db = tmp_path / "oeis.db"
    build_index(stripped, names, db, max_terms=10)

    query = parse_query("1,2,3,4,5", allow_subsequence=False)
    transforms = default_transforms(scale_values=(2,), shift_values=(), allow_diff=False, allow_partial_sum=False, allow_abs=False)

    matches = search_transform_matches(
        query,
        db,
        max_depth=1,
        transforms=transforms,
        limit=5,
        snippet_len=5,
    )

    ids = [m.id for m in matches]
    assert "A100000" in ids
    hit = next(m for m in matches if m.id == "A100000")
    assert hit.transform_desc is not None and "scale(2)" in hit.transform_desc
