from __future__ import annotations

import json
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]


def test_public_json_schemas_are_draft_2020_objects():
    schema_dir = REPOSITORY / "src/vibethinker_experiments/evaluation/schemas"
    expected = {
        "evaluation-profile.schema.json",
        "panel-row.schema.json",
        "generation-result.schema.json",
        "judgment.schema.json",
        "panel-manifest.schema.json",
        "scored-result.schema.json",
    }
    assert {path.name for path in schema_dir.glob("*.json")} == expected
    for path in schema_dir.glob("*.json"):
        schema = json.loads(path.read_text())
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["type"] == "object"
