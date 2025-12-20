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

