from __future__ import annotations

from vibethinker_experiments.evaluation.judge import (
    compact_judgments,
    judge_one,
    judge_signature,
    pending_for_retry,
)


class FailingTransport:
    def post_json(self, payload):
        raise RuntimeError("synthetic transient failure")


class CorrectTransport:
    def post_json(self, payload):
        return {"verdict": "correct", "confidence": 0.99, "brief_reason": "synthetic"}


def test_retry_is_idempotent_and_compacts_by_panel_id(toy_rows, generation_results):
    panel_by_id = {row["panel_id"]: row for row in toy_rows}
    generation = generation_results[0]
    signature = judge_signature({"model": "synthetic-judge", "temperature": 0})
    first = judge_one(
        panel_by_id[generation["panel_id"]],
        generation,
        transport=FailingTransport(),
        model="synthetic-judge",
        signature=signature,
        attempt=1,
    )
    assert first["judge_status"] == "unresolved"
    pending = pending_for_retry([generation], [first], signature=signature)
    assert pending == [(generation, 2)]

    second = judge_one(
        panel_by_id[generation["panel_id"]],
        generation,
        transport=CorrectTransport(),
        model="synthetic-judge",
        signature=signature,
        attempt=pending[0][1],
    )
    compact = compact_judgments([first, second, first, second])
    assert len(compact) == 1
    assert compact[0]["attempt"] == 2
    assert compact[0]["judge_status"] == "correct"
    assert pending_for_retry([generation], compact, signature=signature) == []


def test_changed_generation_hash_forces_retry(generation_results):
    generation = generation_results[0]
    signature = judge_signature({"model": "synthetic"})
    old = {
        "panel_id": generation["panel_id"],
        "generation_sha256": "0" * 64,
        "judge_signature": signature,
        "judge_status": "correct",
        "attempt": 3,
    }
    assert pending_for_retry([generation], [old], signature=signature) == [(generation, 4)]
