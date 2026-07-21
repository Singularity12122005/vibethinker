"""Build the frozen OpenThinker3 Skywork math/code RL pool."""

from __future__ import annotations

import argparse
import copy
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

from .data_contract import (
    difficulty_ok,
    load_data_contract,
    prompt_fingerprint,
    prompt_has_damaged_characters,
    prompt_tokens,
    sha256,
    valid_code,
    valid_math,
)


def normalize_selected_row(row: dict[str, Any], pool: str, repeat_copy: int) -> dict[str, Any]:
    normalized = copy.deepcopy(row)
    raw_gold = normalized["reward_model"]["ground_truth"]
    gold = json.loads(raw_gold) if isinstance(raw_gold, str) else raw_gold
    if normalized["ability"] == "math" and isinstance(gold, str):
        gold = [gold]
    normalized["reward_model"]["ground_truth"] = json.dumps(
        gold, ensure_ascii=False, separators=(",", ":")
    )
    normalized["extra_info"]["selected_pool"] = pool
    normalized["extra_info"]["repeat_copy"] = repeat_copy
    return normalized


def _load_rows(paths: list[Path]) -> list[dict[str, Any]]:
    import pyarrow as pa
    import pyarrow.parquet as pq

    return pa.concat_tables([pq.read_table(path) for path in paths]).to_pylist()


def build_dataset(
    *,
    input_dir: Path,
    output_dir: Path,
    tokenizer: Any,
    contract: dict[str, Any],
) -> dict[str, Any]:
    import pyarrow as pa
    import pyarrow.parquet as pq

    source_files: dict[str, str] = contract["source"]["files"]
    source_paths = [input_dir / "data" / name for name in source_files]
    for path in source_paths:
        actual = sha256(path)
        expected = source_files[path.name]
        if actual != expected:
            raise RuntimeError(
                f"source SHA mismatch for {path.name}: expected={expected} actual={actual}"
            )

    selection = contract["selection"]
    difficulty = selection["difficulty"]
    max_prompt_tokens = int(selection["max_prompt_tokens"])
    rejected: Counter[str] = Counter()
    candidates: dict[str, list[dict[str, Any]]] = {"math": [], "code": []}
    seen: dict[str, set[str]] = {"math": set(), "code": set()}
    route_counts: Counter[str] = Counter()

    for row in _load_rows(source_paths):
        ability = row.get("ability")
        if ability not in candidates:
            rejected["wrong_ability"] += 1
            continue
        if not difficulty_ok(
            row,
            difficulty["key"],
            int(difficulty["minimum"]),
            int(difficulty["maximum"]),
        ):
            rejected[f"{ability}_difficulty"] += 1
            continue
        if ability == "math":
            valid = valid_math(row)
            route = None
        else:
            valid, route = valid_code(row)
        if not valid:
            rejected[f"{ability}_invalid"] += 1
            continue
        if prompt_has_damaged_characters(row):
            rejected[f"{ability}_damaged_characters"] += 1
            continue
        if prompt_tokens(row, tokenizer) > max_prompt_tokens:
            rejected[f"{ability}_prompt_too_long"] += 1
            continue
        fingerprint = prompt_fingerprint(row)
        if fingerprint in seen[ability]:
            rejected[f"{ability}_duplicate_prompt"] += 1
            continue
        seen[ability].add(fingerprint)
        candidates[ability].append(row)
        if route:
            route_counts[route] += 1

    math_count = int(selection["math_unique"])
    code_count = int(selection["code_unique"])
    if len(candidates["math"]) < math_count or len(candidates["code"]) < code_count:
        raise RuntimeError(
            "insufficient valid candidates: "
            f"math={len(candidates['math'])}/{math_count}, "
            f"code={len(candidates['code'])}/{code_count}"
        )

    seed = int(selection["seed"])
    rng = random.Random(seed)
    rng.shuffle(candidates["math"])
    rng.shuffle(candidates["code"])
    math_rows = [normalize_selected_row(row, "math", 0) for row in candidates["math"][:math_count]]
    code_rows = [normalize_selected_row(row, "code", 0) for row in candidates["code"][:code_count]]
    code_copies = int(selection["code_copies"])
    combined = list(math_rows)
    for copy_index in range(code_copies):
        combined.extend(
            normalize_selected_row(row, "code", copy_index)
            for row in candidates["code"][:code_count]
        )
    random.Random(seed + 1).shuffle(combined)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths = {
        "math": output_dir / "math.parquet",
        "code": output_dir / "code.parquet",
        "train": output_dir / "train.parquet",
    }
    pq.write_table(pa.Table.from_pylist(math_rows), output_paths["math"], compression="zstd")
    pq.write_table(pa.Table.from_pylist(code_rows), output_paths["code"], compression="zstd")
    pq.write_table(pa.Table.from_pylist(combined), output_paths["train"], compression="zstd")

    token_counts = [prompt_tokens(row, tokenizer) for row in math_rows + code_rows]
    manifest = {
        "schema_version": 1,
        "formal_id": contract["formal_id"],
        "source": {
            "repository": contract["source"]["repository"],
            "revision": contract["source"]["revision"],
            "files": {
                path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
                for path in source_paths
            },
        },
        "tokenizer": contract["tokenizer"],
        "selection": selection,
        "rows": {
            "math_candidates": len(candidates["math"]),
            "code_candidates": len(candidates["code"]),
            "math_unique": len(math_rows),
            "code_unique": len(code_rows),
            "train_materialized": len(combined),
        },
        "prompt_tokens": {
            "min": min(token_counts),
            "max": max(token_counts),
            "mean": sum(token_counts) / len(token_counts),
        },
        "route_counts_candidates": dict(sorted(route_counts.items())),
        "rejected": dict(sorted(rejected.items())),
        "files": {
            path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in output_paths.values()
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--tokenizer-path", type=Path, required=True)
    args = parser.parse_args()

    from transformers import AutoTokenizer

    contract = load_data_contract(args.contract)
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_path, local_files_only=True)
    manifest = build_dataset(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        tokenizer=tokenizer,
        contract=contract,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
