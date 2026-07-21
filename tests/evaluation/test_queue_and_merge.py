from __future__ import annotations

import pytest

from vibethinker_experiments.evaluation.io import write_jsonl
from vibethinker_experiments.evaluation.queue import WorkQueue, merge_result_shards


def test_queue_claim_recover_and_complete_are_idempotent(tmp_path):
    rows = [
        {"panel_id": "synthetic-a", "value": 1},
        {"panel_id": "synthetic-b", "value": 2},
    ]
    queue = WorkQueue(tmp_path / "queue")
    queue.initialize(rows)
    claimed, row = queue.claim("worker-0")
    assert row["panel_id"] in {"synthetic-a", "synthetic-b"}
    queue.recover()
    assert queue.state() == {"pending": 2, "running": 0, "done": 0}
    claimed_again, _ = queue.claim("worker-0")
    queue.complete(claimed_again)
    queue.complete(claimed_again)
    assert queue.state() == {"pending": 1, "running": 0, "done": 1}


def test_merge_follows_panel_order_and_rejects_duplicates(tmp_path):
    panel = [{"panel_id": "a"}, {"panel_id": "b"}]
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    write_jsonl(first, [{"panel_id": "b", "score": 2}])
    write_jsonl(second, [{"panel_id": "a", "score": 1}])
    assert [row["panel_id"] for row in merge_result_shards(panel, [first, second])] == [
        "a",
        "b",
    ]
    write_jsonl(second, [{"panel_id": "b", "score": 3}])
    with pytest.raises(ValueError, match="duplicate result"):
        merge_result_shards(panel, [first, second])
