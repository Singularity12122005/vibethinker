"""Shared, dependency-light data validation for build and independent audit."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

ALL_CODE_ROUTES = ("question_id", "import_prefix", "inputs", "assert_case")
SELF_CONTAINED_CODE_ROUTES = ("import_prefix", "inputs", "assert_case")


def load_data_contract(path: str | Path) -> dict[str, Any]:
    contract = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(contract, dict) or contract.get("schema_version") != 1:
        raise ValueError("unsupported OpenThinker3 data contract")
    return contract


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prompt_text(row: dict[str, Any]) -> str:
    prompt = row.get("prompt")
    if not isinstance(prompt, list) or len(prompt) != 1:
        raise ValueError("prompt must contain exactly one message")
    message = prompt[0]
    if not isinstance(message, dict) or message.get("role") != "user":
        raise ValueError("prompt message must have role=user")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("prompt content must be non-empty")
    return content


def parse_ground_truth(row: dict[str, Any]) -> Any:
    reward_model = row.get("reward_model")
    if not isinstance(reward_model, dict) or reward_model.get("style") != "rule":
        raise ValueError("reward_model.style must be rule")
    value = reward_model.get("ground_truth")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("ground_truth must be a non-empty JSON string")
    return json.loads(value)


def route_present(gold: dict[str, Any], route: str) -> bool:
    value = gold.get(route)
    if route == "question_id":
        return isinstance(value, (str, int)) and bool(str(value).strip())
    if route == "import_prefix":
        test_code = gold.get("test_code")
        return (
            isinstance(value, str)
            and isinstance(test_code, str)
            and len([line for line in test_code.splitlines() if line.strip()]) >= 2
            and isinstance(gold.get("entry_point"), str)
            and bool(gold["entry_point"].strip())
        )
    if route == "inputs":
        outputs = gold.get("outputs")
        return (
            isinstance(value, list)
            and isinstance(outputs, list)
            and bool(value)
            and len(value) == len(outputs)
            and all(item is not None for item in value + outputs)
        )
    if route == "assert_case":
        return (
            isinstance(value, list)
            and bool(value)
            and all(isinstance(item, str) and item.strip() for item in value)
        )
    raise AssertionError(route)


def valid_math(row: dict[str, Any]) -> bool:
    try:
        prompt_text(row)
        gold = parse_ground_truth(row)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    if isinstance(gold, str):
        return bool(gold.strip())
    return (
        isinstance(gold, list)
        and bool(gold)
        and all(isinstance(item, str) and item.strip() for item in gold)
    )


def valid_code(row: dict[str, Any]) -> tuple[bool, str | None]:
    try:
        prompt_text(row)
        gold = parse_ground_truth(row)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False, None
    if not isinstance(gold, dict):
        return False, None
    routes = [route for route in ALL_CODE_ROUTES if route_present(gold, route)]
    if len(routes) != 1 or routes[0] not in SELF_CONTAINED_CODE_ROUTES:
        return False, None
    return True, routes[0]


def difficulty_ok(row: dict[str, Any], key: str, minimum: int, maximum: int) -> bool:
    try:
        difficulty = row["extra_info"]["model_difficulty"][key]
    except (KeyError, TypeError):
        return False
    return isinstance(difficulty, int) and minimum <= difficulty <= maximum


def prompt_fingerprint(row: dict[str, Any]) -> str:
    normalized = unicodedata.normalize("NFKC", " ".join(prompt_text(row).split())).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def prompt_has_damaged_characters(row: dict[str, Any]) -> bool:
    for character in prompt_text(row):
        if character == "\ufffd":
            return True
        if unicodedata.category(character) in {"Cc", "Cs"} and character not in "\n\r\t":
            return True
    return False


def prompt_tokens(row: dict[str, Any], tokenizer: Any) -> int:
    token_ids = tokenizer.apply_chat_template(
        row["prompt"], tokenize=True, add_generation_prompt=True
    )
    if isinstance(token_ids, Mapping):
        token_ids = token_ids["input_ids"]
    if token_ids and isinstance(token_ids[0], list):
        if len(token_ids) != 1:
            raise ValueError("expected one tokenized conversation")
        token_ids = token_ids[0]
    return len(token_ids)
