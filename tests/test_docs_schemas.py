import json
from pathlib import Path


def test_docs_schema_files_are_valid_json():
    root = Path(__file__).resolve().parents[1]
    schema_dir = root / "docs" / "schemas"
    assert schema_dir.is_dir()
    for name in ("analyze.schema.json", "combo.schema.json"):
        path = schema_dir / name
        data = json.loads(path.read_text())
        assert isinstance(data, dict)
        assert "$schema" in data
        assert data.get("type") == "object"

