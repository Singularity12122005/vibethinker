from vibethinker_experiments.qwen25.code_verifier import run_test_harness


def test_harness_accepts_valid_candidate():
    result = run_test_harness(
        "def add(a, b): return a + b",
        "def check(fn):\n    assert fn(2, 3) == 5",
        "add",
    )
    assert result.returncode == 0


def test_harness_reports_assertion_failure():
    result = run_test_harness(
        "def add(a, b): return 0",
        "def check(fn):\n    assert fn(2, 3) == 5",
        "add",
    )
    assert result.returncode != 0
