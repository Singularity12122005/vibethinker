import hashlib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_all_declared_patches_exist_and_match_their_hashes() -> None:
    manifests = sorted((ROOT / "patches").glob("*/manifest.yaml"))
    assert {path.parent.name for path in manifests} == {
        "verl-math-rl",
        "verl-openthinker3",
        "vllm-openthinker3",
    }
    for manifest_path in manifests:
        manifest = yaml.safe_load(manifest_path.read_text())
        assert manifest["schema_version"] == 1
        assert manifest["patches"]
        for patch in manifest["patches"]:
            patch_path = manifest_path.parent / patch["file"]
            assert patch_path.is_file()
            digest = hashlib.sha256(patch_path.read_bytes()).hexdigest()
            assert digest == patch["sha256"]


def test_math_rl_patch_commits_before_tracking_and_validates_resume() -> None:
    patch = (
        ROOT / "patches/verl-math-rl/0001-checkpoint-schedule-and-commit-marker.patch"
    ).read_text()
    assert patch.index("marker = mark_checkpoint_committed") < patch.index(
        'with open(local_latest_checkpointed_iteration, "w")'
    )
    assert "validate_committed_checkpoint(global_step_folder)" in patch
