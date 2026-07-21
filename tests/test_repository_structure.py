from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAINLINES = {
    "qwen25-15k",
    "qwen25-30k",
    "qwen35-30k",
    "openthinker3-skywork",
}


def test_public_experiment_surface_contains_only_four_mainlines() -> None:
    experiments = ROOT / "experiments"
    observed = {
        path.name
        for path in experiments.iterdir()
        if path.is_dir() and (path / "README.md").is_file()
    }
    assert observed == MAINLINES
    assert {path.name for path in experiments.iterdir() if path.is_file()} == {"README.md"}


def test_legacy_qwen25_surface_is_removed() -> None:
    package_root = ROOT / "src" / "vibethinker_experiments"
    test_root = ROOT / "tests"
    assert all(not list(path.glob("*.py")) for path in package_root.glob("legacy*"))
    assert all(not list(path.glob("*.py")) for path in test_root.glob("legacy*"))


def test_asset_placeholders_and_frozen_configs_exist() -> None:
    for mainline in MAINLINES:
        assert (ROOT / "data" / mainline / "README.md").is_file()
    assert (ROOT / "checkpoints" / "README.md").is_file()
    assert (ROOT / "results" / "README.md").is_file()

    expected_configs = {
        "configs/qwen25/sft_15k.yaml",
        "configs/qwen25/sft_30k_native.yaml",
        "configs/qwen25/verl_math500_64k.yaml",
        "configs/qwen35/sft_30k_lora.yaml",
        "configs/qwen35/verl_128k_base.yaml",
        "configs/qwen35/verl_128k_math500.yaml",
        "configs/qwen35/verl_128k_mix1k.yaml",
        "configs/openthinker3/data.yaml",
        "configs/openthinker3/train.yaml",
    }
    assert all((ROOT / path).is_file() for path in expected_configs)
