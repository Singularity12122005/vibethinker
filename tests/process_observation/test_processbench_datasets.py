from __future__ import annotations

import pytest

from vibethinker_experiments.process_observation.datasets import (
    PROCESSBENCH_OFFICIAL_LABEL_SEMANTICS,
    PROCESSBENCH_OFFICIAL_SPLITS,
    ProcessBenchSourceUnavailable,
    TraceRenderingPolicy,
    aggressive_duplicate_review_sha256,
    build_processbench_inventory,
    build_semantics_source_receipts,
    build_snapshot_manifest,
    conservative_normalized_problem_sha256,
    external_macro_region_for_example,
    import_processbench_split,
    load_processbench_source,
    load_selection_manifest,
    matched_correct_step,
    render_external_trace,
    select_processbench_pilot,
    validate_discovery_confirmation_no_leakage,
    validate_unique_selected_problem_hashes,
    write_split_selection_manifests,
)
from vibethinker_experiments.process_observation.identity import canonical_jsonl_bytes


def _row(split: str, index: int, *, label: int, generator: str, steps: int = 4):
    return {
        "final_answer_correct": label == -1,
        "generator": generator,
        "id": f"{split}-{index:02d}",
        "label": label,
        "problem": f"Synthetic {split} problem {index}",
        "steps": [f"Synthetic step {step} for {split}-{index}" for step in range(steps)],
    }


def _balanced_records():
    records = []
    generators = ["gen-a", "gen-b", "gen-c", "gen-d"]
    for split in PROCESSBENCH_OFFICIAL_SPLITS:
        rows = []
        for index, label in enumerate([0, 1, 2, 3]):
            rows.append(_row(split, index, label=label, generator=generators[index], steps=4))
        for index in range(4, 8):
            rows.append(_row(split, index, label=-1, generator=generators[index % 4], steps=5))
        records.extend(
            import_processbench_split(
                rows,
                source_split=split,
                source_revision="synthetic-processbench-fixture-v1",
            )
        )
    return records


def _record_from_row(split: str, row: dict):
    return import_processbench_split(
        [row],
        source_split=split,
        source_revision="synthetic-revision",
    )[0]


def test_processbench_official_field_preservation_and_label_semantics():
    example = import_processbench_split(
        [_row("gsm8k", 1, label=2, generator="gen-a", steps=4)],
        source_split="gsm8k",
        source_revision="synthetic-revision",
    )[0]

    assert PROCESSBENCH_OFFICIAL_LABEL_SEMANTICS["step_indexing"] == "zero_based"
    assert PROCESSBENCH_OFFICIAL_LABEL_SEMANTICS["all_correct_sentinel"] == -1
    assert example.source_record_id == "gsm8k-01"
    assert example.generator == "gen-a"
    assert example.raw_label == 2
    assert example.final_answer_correct is False
    assert example.earliest_error_step_index == 2
    assert example.normalized_error_position == pytest.approx(0.625)
    assert example.role_record.raw_source_sha256 is not None
    assert (
        example.conservative_normalized_problem_sha256
        == example.role_record.normalized_problem_sha256
    )
    assert example.aggressive_duplicate_review_sha256 == aggressive_duplicate_review_sha256(
        example.problem
    )


def test_processbench_malformed_label_rejection_and_all_correct_sentinel():
    with pytest.raises(ValueError, match="zero-based step index"):
        import_processbench_split(
            [_row("math", 1, label=4, generator="gen-a", steps=4)],
            source_split="math",
            source_revision="synthetic-revision",
        )

    with pytest.raises(ValueError, match="label must be an integer"):
        import_processbench_split(
            [{**_row("math", 2, label=-1, generator="gen-a"), "label": "-1"}],
            source_split="math",
            source_revision="synthetic-revision",
        )

    all_correct = import_processbench_split(
        [_row("math", 3, label=-1, generator="gen-a", steps=3)],
        source_split="math",
        source_revision="synthetic-revision",
    )[0]
    assert all_correct.is_all_correct is True
    assert all_correct.normalized_error_position is None


def test_processbench_duplicate_source_ids_are_rejected():
    row = _row("gsm8k", 1, label=-1, generator="gen-a")
    with pytest.raises(ValueError, match="duplicate ProcessBench id"):
        import_processbench_split(
            [row, row],
            source_split="gsm8k",
            source_revision="synthetic-revision",
        )


def test_processbench_inventory_counts_and_duplicate_hashes():
    records = _balanced_records()
    inventory = build_processbench_inventory(
        records,
        source_revision="synthetic-processbench-fixture-v1",
        source_license="apache-2.0",
    )

    assert inventory["complete"] is True
    assert inventory["splits"]["gsm8k"]["row_count"] == 8
    assert inventory["splits"]["gsm8k"]["error_count"] == 4
    assert inventory["splits"]["gsm8k"]["all_correct_count"] == 4
    assert inventory["splits"]["gsm8k"]["label_final_answer_crosstab"] == {
        "label_all_correct__final_answer_correct_false": 0,
        "label_all_correct__final_answer_correct_true": 4,
        "label_error__final_answer_correct_false": 4,
        "label_error__final_answer_correct_true": 0,
    }
    assert inventory["splits"]["gsm8k"]["split_generator_trace_status"]["gen-a"] == {
        "label_all_correct__final_correct": 1,
        "label_error__final_wrong": 1,
    }
    assert inventory["splits"]["gsm8k"]["number_of_steps_distribution"] == {4: 4, 5: 4}
    assert inventory["conservative_duplicate_hashes_across_splits"] == {}


def test_label_and_final_answer_crosstab_keeps_semantics_distinct():
    rows = [
        {**_row("gsm8k", 1, label=-1, generator="gen-a"), "final_answer_correct": True},
        {**_row("gsm8k", 2, label=-1, generator="gen-a"), "final_answer_correct": False},
        {**_row("gsm8k", 3, label=0, generator="gen-a"), "final_answer_correct": False},
        {**_row("gsm8k", 4, label=1, generator="gen-a"), "final_answer_correct": True},
    ]
    records = import_processbench_split(
        rows,
        source_split="gsm8k",
        source_revision="synthetic-revision",
    )
    inventory = build_processbench_inventory(
        records,
        source_revision="synthetic-revision",
        source_license="apache-2.0",
    )

    assert inventory["splits"]["gsm8k"]["label_final_answer_crosstab"] == {
        "label_all_correct__final_answer_correct_false": 1,
        "label_all_correct__final_answer_correct_true": 1,
        "label_error__final_answer_correct_false": 1,
        "label_error__final_answer_correct_true": 1,
    }
    assert inventory["splits"]["gsm8k"]["error_but_final_correct_count"] == 1
    assert inventory["splits"]["gsm8k"]["all_correct_but_final_wrong_count"] == 1


def test_matched_correct_step_uses_error_position_not_last_step():
    assert matched_correct_step((1 + 0.5) / 4, 6) == 2
    assert matched_correct_step(0.99, 3) == 2


def test_processbench_deterministic_selection_and_split_balance():
    records = _balanced_records()
    inventory = build_processbench_inventory(
        records,
        source_revision="synthetic-processbench-fixture-v1",
        source_license="apache-2.0",
    )
    rows_a, report_a = select_processbench_pilot(records, inventory=inventory, seed=123)
    rows_b, report_b = select_processbench_pilot(records, inventory=inventory, seed=123)

    assert rows_a == rows_b
    assert report_a == report_b
    assert len(rows_a) == 32
    assert report_a["sampling_pair_count"] == 16
    assert report_a["sampling_pairs"][0]["pair_kind"] == "position_matched_sampling_control"
    for split, composition in report_a["split_composition"].items():
        assert composition["row_count"] == 8, split
        assert composition["erroneous"] == 4
        assert composition["all_correct"] == 4
        assert composition["discovery"] == 4
        assert composition["confirmation"] == 4
        assert len(composition["generators"]) == 4


def test_processbench_generator_aware_matching_prefers_same_generator():
    error = _record_from_row("gsm8k", _row("gsm8k", 1, label=1, generator="gen-a", steps=4))
    same_generator = _record_from_row(
        "gsm8k", _row("gsm8k", 2, label=-1, generator="gen-a", steps=7)
    )
    other_generator = _record_from_row(
        "gsm8k", _row("gsm8k", 3, label=-1, generator="gen-b", steps=4)
    )
    records = [error, same_generator, other_generator]
    inventory = build_processbench_inventory(
        records,
        source_revision="synthetic-revision",
        source_license="apache-2.0",
    )
    rows, report = select_processbench_pilot(records, inventory=inventory, seed=1)

    assert report["sampling_pairs"][0]["correct_record_id"] == same_generator.source_record_id
    assert report["sampling_pairs"][0]["deterministic_pairing_score"]["generator_matched"] is True
    control = [row for row in rows if row["sampling_pair_role"] == "position_matched_control"][0]
    assert control["pairing_metadata"]["generator_matched"] is True
    assert "position_distance" in control["pairing_metadata"]
    assert "log_step_count_distance" in control["pairing_metadata"]


def test_processbench_selection_requires_completed_inventory():
    with pytest.raises(ValueError, match="inventory must be complete"):
        select_processbench_pilot(_balanced_records(), inventory={"complete": False})


def test_processbench_no_discovery_confirmation_leakage_and_duplicate_hash_rejection():
    rows, _ = select_processbench_pilot(
        _balanced_records(),
        inventory=build_processbench_inventory(
            _balanced_records(),
            source_revision="synthetic-processbench-fixture-v1",
            source_license="apache-2.0",
        ),
    )
    validate_discovery_confirmation_no_leakage(rows)

    leaked = [
        {**rows[0], "discovery_or_confirmation": "discovery"},
        {**rows[0], "problem_id": "different", "discovery_or_confirmation": "confirmation"},
    ]
    with pytest.raises(ValueError, match="normalized-problem leakage"):
        validate_discovery_confirmation_no_leakage(leaked)
    with pytest.raises(ValueError, match="duplicate normalized-problem hash"):
        validate_unique_selected_problem_hashes(leaked)


def test_external_and_native_trace_provenance_are_separate_and_not_aru():
    records = _balanced_records()
    inventory = build_processbench_inventory(
        records,
        source_revision="synthetic-processbench-fixture-v1",
        source_license="apache-2.0",
    )
    rows, _ = select_processbench_pilot(records, inventory=inventory)
    first = rows[0]

    assert first["trace_provenance"] == "external_benchmark_trace"
    assert first["external_macro_region"]["region_kind"] == "external_macro_region"
    assert first["native_trace_arm"]["trace_provenance"] == "target_checkpoint_native"
    assert first["native_trace_arm"]["processbench_label_used_for_region_selection"] is False
    assert "aru_id" not in first
    assert first["sampling_pair_kind"] == "position_matched_sampling_control"


def test_external_macro_region_for_all_correct_requires_matched_position():
    error = import_processbench_split(
        [_row("omnimath", 1, label=1, generator="gen-a", steps=3)],
        source_split="omnimath",
        source_revision="synthetic-revision",
    )[0]
    correct = import_processbench_split(
        [_row("omnimath", 2, label=-1, generator="gen-b", steps=3)],
        source_split="omnimath",
        source_revision="synthetic-revision",
    )[0]

    assert external_macro_region_for_example(error).processbench_label_role == (
        "gold_earliest_error_macro_step"
    )
    with pytest.raises(ValueError, match="matched macro-step"):
        external_macro_region_for_example(correct)
    assert external_macro_region_for_example(
        correct, matched_all_correct_step=1
    ).region_kind == "external_macro_region"


def test_processbench_loader_is_network_disabled_by_default():
    with pytest.raises(ProcessBenchSourceUnavailable, match="network-disabled by default"):
        load_processbench_source()


def test_raw_benchmark_text_is_not_written_to_public_selection_outputs(tmp_path):
    records = _balanced_records()
    inventory = build_processbench_inventory(
        records,
        source_revision="synthetic-processbench-fixture-v1",
        source_license="apache-2.0",
    )
    rows, report = select_processbench_pilot(records, inventory=inventory)
    discovery_jsonl = tmp_path / "discovery.jsonl"
    confirmation_jsonl = tmp_path / "confirmation.jsonl"
    output_report = tmp_path / "selection.md"
    write_split_selection_manifests(
        rows,
        report,
        discovery_jsonl=discovery_jsonl,
        confirmation_jsonl=confirmation_jsonl,
        output_report=output_report,
    )

    text = discovery_jsonl.read_text(encoding="utf-8") + confirmation_jsonl.read_text(
        encoding="utf-8"
    )
    assert "Synthetic step" not in text
    assert "Synthetic gsm8k problem" not in text
    assert "source_record_id" in text


def test_confirmation_manifest_is_sealed_until_explicit_unseal(tmp_path):
    records = _balanced_records()
    inventory = build_processbench_inventory(
        records,
        source_revision="synthetic-processbench-fixture-v1",
        source_license="apache-2.0",
    )
    rows, report = select_processbench_pilot(records, inventory=inventory)
    discovery_jsonl = tmp_path / "discovery.jsonl"
    confirmation_jsonl = tmp_path / "confirmation.jsonl"
    output_report = tmp_path / "selection.md"
    write_split_selection_manifests(
        rows,
        report,
        discovery_jsonl=discovery_jsonl,
        confirmation_jsonl=confirmation_jsonl,
        output_report=output_report,
    )

    assert load_selection_manifest(discovery_jsonl, intended_split="discovery")
    with pytest.raises(ValueError, match="confirmation manifest is sealed"):
        load_selection_manifest(confirmation_jsonl, intended_split="confirmation")
    assert load_selection_manifest(
        confirmation_jsonl,
        intended_split="confirmation",
        unseal_confirmation=True,
    )


def test_trace_rendering_policy_identity_and_character_spans_are_canonical():
    example = import_processbench_split(
        [_row("olympiadbench", 1, label=0, generator="gen-a", steps=2)],
        source_split="olympiadbench",
        source_revision="synthetic-revision",
    )[0]
    policy = TraceRenderingPolicy()
    rendered = render_external_trace(example, policy=policy)

    assert policy.policy_id == "processbench-external-macro-text-v1"
    assert policy.tokenization_status == "character_spans_only"
    assert rendered["prompt_token_ids"] is None
    assert rendered["tokenizer_sha256"] is None
    assert rendered["chat_template_sha256"] is None
    assert rendered["canonical_text"].count("\n") == 1
    assert "\r" not in rendered["canonical_text"]
    assert rendered["step_spans"][0]["region_kind"] == "external_macro_region"


def test_canonical_lf_utf8_manifest_bytes():
    records = _balanced_records()
    inventory = build_processbench_inventory(
        records,
        source_revision="synthetic-processbench-fixture-v1",
        source_license="apache-2.0",
    )
    rows, _ = select_processbench_pilot(records, inventory=inventory)
    content = canonical_jsonl_bytes(rows)

    assert content.endswith(b"\n")
    assert b"\r" not in content
    assert not content.startswith(b"\xef\xbb\xbf")


def test_semantics_source_provenance_is_separate_from_dataset_revision():
    receipts = build_semantics_source_receipts(
        evaluation_code_revision="qwenlm-processbench-main-abc123",
        run_eval_sha256="a" * 64,
        critique_template_sha256="b" * 64,
        readme_or_datacard_sha256="c" * 64,
    )
    manifest = build_snapshot_manifest(
        dataset_revision="hf-dataset-sha-123",
        retrieval_method="synthetic-test",
        retrieval_timestamp="2026-07-22T00:00:00Z",
        source_license="apache-2.0",
        source_file_inventory=[],
        raw_split_row_counts={"gsm8k": 0, "math": 0, "olympiadbench": 0, "omnimath": 0},
        semantics_source_receipts=receipts,
    )

    assert manifest["exact_revision"] == "hf-dataset-sha-123"
    assert manifest["semantics_source_receipts"]["evaluation_code_revision"] != (
        manifest["exact_revision"]
    )
    assert manifest["semantics_source_receipts"]["run_eval_sha256"] == "a" * 64


def test_conservative_duplicate_is_hard_and_aggressive_collision_is_review_only():
    conservative_a = conservative_normalized_problem_sha256("Compute x + y.")
    conservative_b = conservative_normalized_problem_sha256("Compute x+y")
    assert conservative_a != conservative_b
    assert aggressive_duplicate_review_sha256(
        "Compute x + y."
    ) == aggressive_duplicate_review_sha256("Compute x+y")
    rows = [
        _row("gsm8k", 1, label=0, generator="gen-a"),
        {**_row("math", 1, label=-1, generator="gen-b"), "problem": "Synthetic gsm8k problem 1"},
        {**_row("omnimath", 2, label=-1, generator="gen-c"), "problem": "Compute x + y."},
        {
            **_row("olympiadbench", 3, label=-1, generator="gen-d"),
            "problem": "Compute x+y",
        },
    ]
    records = []
    for split, row in [
        ("gsm8k", rows[0]),
        ("math", rows[1]),
        ("omnimath", rows[2]),
        ("olympiadbench", rows[3]),
    ]:
        records.extend(
            import_processbench_split(
                [row],
                source_split=split,
                source_revision="synthetic-revision",
            )
        )
    inventory = build_processbench_inventory(
        records,
        source_revision="synthetic-revision",
        source_license="apache-2.0",
    )

    assert inventory["conservative_duplicate_hashes_across_splits"]
    assert inventory["aggressive_duplicate_review_clusters"]
