import json

import pytest

from vibethinker_experiments.common.jsonl import decode_json_records


def test_decodes_pretty_multiline_concatenated_and_array_values() -> None:
    text = """
    {
      "id": 1,
      "text": "valid newline escape: \\n"
    }
    {"id": 2}[{"id": 3}, {"id": 4}]
    """
    report = decode_json_records(text)
    assert [row["id"] for row in report.records] == [1, 2, 3, 4]
    assert report.malformed_segments == 0
    assert report.non_object_values == 0


def test_skips_invalid_raw_newline_string_without_claiming_recovery() -> None:
    text = '{"id":1}\n{"id":"broken\nvalue"}\n{"id":2}\n'
    report = decode_json_records(text)
    assert [row["id"] for row in report.records] == [1, 2]
    assert report.malformed_segments >= 1


def test_counts_non_object_values() -> None:
    report = decode_json_records('1\n[{"id": 1}, "not-a-record"]\n')
    assert report.records == [{"id": 1}]
    assert report.non_object_values == 2


def test_standard_json_rejects_unescaped_newline() -> None:
    with pytest.raises(json.JSONDecodeError):
        json.loads('{"text":"first\nsecond"}')
