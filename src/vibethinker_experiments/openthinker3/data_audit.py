"""Independent contract audit for a built OpenThinker3 RL dataset."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .data_contract import (
    difficulty_ok,
    load_data_contract,
    prompt_fingerprint,
    prompt_has_damaged_characters,
    prompt_text,
    prompt_tokens,
    sha256,
    valid_code,
    valid_math,
)


def audit_dataset(
    *,
    data_dir: Path,
    tokenizer: Any,
    contract: dict[str, Any],
) -> dict[str, Any]:
    import pyarrow.parquet as pq

    train_path = data_dir / "train.parquet"
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    rows = pq.read_table(train_path).to_pylist()
    selection = contract["selection"]
    expected_math = int(selection["math_unique"])
    expected_code = int(selection["code_unique"])
    expected_copies = int(selection["code_copies"])
    expected_total = expected_math + expected_code * expected_copies

    if manifest["formal_id"] != contract["formal_id"]:
        raise RuntimeError("manifest formal_id does not match resolved data contract")
    if len(rows) != expected_total or manifest["rows"]["train_materialized"] != expected_total:
        raise RuntimeError("materialized row count mismatch")
    if manifest["files"][train_path.name]["sha256"] != sha256(train_path):
        raise RuntimeError("train archive SHA mismatch")

    abilities = Counter(row["ability"] for row in rows)
    expected_abilities = Counter(math=expected_math, code=expected_code * expected_copies)
    if abilities != expected_abilities:
        raise RuntimeError(f"ability counts mismatch: {abilities} != {expected_abilities}")

    hashes: Counter[tuple[str, str]] = Counter()
    code_copy_ids: dict[str, set[int]] = {}
    token_counts: list[int] = []
    difficulty = selection["difficulty"]
    for row in rows:
        text = prompt_text(row)
        if "<think>" in text or "</think>" in text:
            raise RuntimeError("prompt contains hidden chain-of-thought tags")
        if not isinstance(row["reward_model"]["ground_truth"], str):
            raise RuntimeError("ground truth is not a JSON boundary string")
        if not difficulty_ok(
            row,
            difficulty["key"],
            int(difficulty["minimum"]),
            int(difficulty["maximum"]),
        ):
            raise RuntimeError("row falls outside the frozen difficulty interval")
        if prompt_has_damaged_characters(row):
            raise RuntimeError("row contains damaged characters")
        if row["ability"] == "math":
            if not valid_math(row) or row["extra_info"]["repeat_copy"] != 0:
                raise RuntimeError("invalid math row")
        else:
            valid, _route = valid_code(row)
            copy_index = row["extra_info"]["repeat_copy"]
            if not valid or copy_index not in range(expected_copies):
                raise RuntimeError("invalid code row")
        fingerprint = prompt_fingerprint(row)
        if row["ability"] == "code":
            code_copy_ids.setdefault(fingerprint, set()).add(copy_index)
        hashes[(row["ability"], fingerprint)] += 1
        token_counts.append(prompt_tokens(row, tokenizer))

    math_hashes = {value for (ability, value) in hashes if ability == "math"}
    code_hashes = {value for (ability, value) in hashes if ability == "code"}
    if len(math_hashes) != expected_math or any(
        count != 1 for (ability, _), count in hashes.items() if ability == "math"
    ):
        raise RuntimeError("math uniqueness contract failed")
    if len(code_hashes) != expected_code or any(
        count != expected_copies for (ability, _), count in hashes.items() if ability == "code"
    ):
        raise RuntimeError("code copy contract failed")
    expected_copy_ids = set(range(expected_copies))
    if any(copy_ids != expected_copy_ids for copy_ids in code_copy_ids.values()):
        raise RuntimeError("code copy identifiers are incomplete")
    if math_hashes & code_hashes:
        raise RuntimeError("math and code prompts overlap")
    if max(token_counts) > int(selection["max_prompt_tokens"]):
        raise RuntimeError("prompt token limit exceeded")

    return {
        "formal_id": contract["formal_id"],
        "rows": len(rows),
        "ability": dict(abilities),
        "unique_math": expected_math,
        "unique_code": expected_code,
        "code_copies_per_prompt": expected_copies,
        "prompt_tokens": {
            "min": min(token_counts),
            "max": max(token_counts),
            "mean": sum(token_counts) / len(token_counts),
        },
        "train_sha256": sha256(train_path),
        "status": "PASS",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--tokenizer-path", type=Path, required=True)
    args = parser.parse_args()

    from transformers import AutoTokenizer

    contract = load_data_contract(args.contract)
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_path, local_files_only=True)
    result = audit_dataset(data_dir=args.data_dir, tokenizer=tokenizer, contract=contract)
    (args.data_dir / "independent_audit.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
