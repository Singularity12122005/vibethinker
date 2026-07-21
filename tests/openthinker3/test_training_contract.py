from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from vibethinker_experiments.openthinker3.platform_adapter import (
    resolve_topology,
    runtime_archive_identity,
    validate_topology,
)
from vibethinker_experiments.openthinker3.training import (
    build_verl_overrides,
    load_training_contract,
)

ROOT = Path(__file__).resolve().parents[2]
TRAIN_CONFIG = ROOT / "configs/openthinker3/train.yaml"


def test_frozen_training_contract_and_rendered_overrides() -> None:
    config = load_training_contract(TRAIN_CONFIG)
    overrides = build_verl_overrides(
        config,
        model_path="/model",
        train_file="/data/train.parquet",
        output_dir="/output",
        ray_address="head.example:6379",
        resume_path="/scratch/global_step_50",
    )
    rendered = "\n".join(overrides)
    for expected in (
        "actor_rollout_ref.rollout.temperature=1.1",
        "actor_rollout_ref.actor.loss_agg_mode=token-mean",
        "actor_rollout_ref.actor.clip_ratio_high=0.28",
        "actor_rollout_ref.actor.ppo_max_token_len_per_gpu=32768",
        "algorithm.use_kl_in_reward=False",
        "reward.reward_manager.name=naive",
        "pkg://vibethinker_experiments.openthinker3.reward",
        "+ray_kwargs.ray_init.address=head.example:6379",
        "trainer.resume_mode=resume_path",
    ):
        assert expected in rendered


def test_runtime_identity_is_injected_by_external_manifest() -> None:
    config = load_training_contract(TRAIN_CONFIG)
    manifest = {
        "schema_version": 1,
        "resolved_config": "openthinker3-skywork-rl-v1",
        "runtime_archive_sha256": "a" * 64,
    }
    archive_sha, resolved_config = runtime_archive_identity(config, manifest)
    assert archive_sha == "a" * 64
    assert resolved_config == "openthinker3-skywork-rl-v1"
    serialized = TRAIN_CONFIG.read_text()
    assert config["formal_runtime_id"] == "REQUIRED_FROM_RUN_MANIFEST"
    assert "formal_runtime_id: sha256:" not in serialized


def test_runtime_manifest_must_match_resolved_config_and_supply_sha() -> None:
    config = load_training_contract(TRAIN_CONFIG)
    with pytest.raises(ValueError, match="resolved_config"):
        runtime_archive_identity(
            config,
            {
                "resolved_config": "different-config",
                "runtime_archive_sha256": "a" * 64,
            },
        )
    with pytest.raises(ValueError, match="64-hex"):
        runtime_archive_identity(
            config,
            {
                "resolved_config": config["resolved_config"],
                "runtime_archive_sha256": "REQUIRED",
            },
        )


def test_platform_aliases_resolve_without_vendor_specific_ids() -> None:
    platform = yaml.safe_load((ROOT / "configs/openthinker3/platform.example.yaml").read_text())
    training = load_training_contract(TRAIN_CONFIG)
    topology = resolve_topology(
        platform,
        {
            "RANK": "2",
            "WORLD_NODES": "4",
            "HEAD_ADDR": "head.example",
            "HEAD_PORT": "7000",
        },
    )
    validate_topology(topology, training)
    assert topology.node_rank == 2
    assert topology.node_count == 4


def test_verl_manifest_covers_exactly_seven_modified_files() -> None:
    manifest = yaml.safe_load((ROOT / "patches/verl-openthinker3/manifest.yaml").read_text())
    patch = (
        ROOT / "patches/verl-openthinker3/0001-openthinker3-training-contract.patch"
    ).read_text()
    diff_files = re.findall(r"^diff --git a/(\S+) b/\S+$", patch, re.MULTILINE)
    assert manifest["upstream"]["commit"] == "7aed6b230776f963fa09509c10d9c3a767d1102c"
    assert len(manifest["changed_files"]) == 7
    assert diff_files == manifest["changed_files"]


def test_vllm_patch_status_is_explicit() -> None:
    manifest = yaml.safe_load((ROOT / "patches/vllm-openthinker3/manifest.yaml").read_text())
    assert manifest["upstream"]["tag"] == "v0.19.0"
    assert manifest["patches"][0]["status"] == "reviewable-parse-checked-not-apply-checked"


def test_launcher_exports_contract_before_ray() -> None:
    launcher = (ROOT / "configs/openthinker3/launch_multinode.sh").read_text()
    assert "VT_RUNTIME_MANIFEST:?set VT_RUNTIME_MANIFEST" in launcher
    assert "VT_SKYWORK_VERIFIER:?set VT_SKYWORK_VERIFIER" in launcher
    assert '--runtime-manifest "$RUNTIME_MANIFEST"' in launcher
    ray_start = launcher.index("ray start --head")
    assert launcher.index("openthinker3.verifier --smoke-test") < ray_start
    for value in (
        "export VT_FORMAL_RUNTIME=1",
        "export VT_REPLICATED_DP_CHECKPOINT=1",
        "export VT_SAVE_FIRST_STEP_CHECKPOINT=1",
        "export VT_ADAPTIVE_ENTROPY_ENABLED=1",
        "export VT_VERIFIER_TIMEOUT_SECONDS=330",
    ):
        assert launcher.index(value) < ray_start


def test_migrated_tree_contains_no_known_internal_identifiers() -> None:
    roots = [
        ROOT / "src/vibethinker_experiments/openthinker3",
        ROOT / "configs/openthinker3",
        ROOT / "tests/openthinker3",
        ROOT / "patches/verl-openthinker3",
        ROOT / "patches/vllm-openthinker3",
    ]
    forbidden = (
        "registry." + "dp.tech",
        "--" + "team ",
        "TRISOL_" + "JOB_ID",
        "/" + "Users/",
        "infra" + "-spot",
    )
    for root in roots:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {
                ".json",
                ".md",
                ".patch",
                ".py",
                ".sh",
                ".yaml",
                ".yml",
            }:
                text = path.read_text(errors="ignore")
                assert not any(value in text for value in forbidden), path
