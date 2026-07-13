import json
from pathlib import Path


def test_docs_regressions_json_is_valid():
    root = Path(__file__).resolve().parents[1]
    path = root / "docs" / "regressions.json"
    data = json.loads(path.read_text())
    assert isinstance(data, list)
    assert data, "regressions.json should contain at least one case"
    for case in data:
        assert isinstance(case, dict)
        assert "name" in case and isinstance(case["name"], str) and case["name"]
        assert "query" in case and isinstance(case["query"], str) and case["query"]
        if "opts" in case:
            assert isinstance(case["opts"], dict)
        if "expect" in case:
            assert isinstance(case["expect"], dict)
        if "requires_ids" in case:
            assert case["requires_ids"] and all(isinstance(seq_id, str) for seq_id in case["requires_ids"])


def test_docs_regressions_cover_all_core_explanation_families():
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "docs" / "regressions.json").read_text())
    expected_keys = {key for case in data for key in (case.get("expect") or {})}
    assert {
        "exact_top",
        "transform_contains",
        "combo_contains_ids",
        "pointwise_contains_ids",
        "convolution_contains_ids",
        "modclass_contains_ids",
        "ranked_families_contains",
    } <= expected_keys
