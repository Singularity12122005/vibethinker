from vibethinker_experiments.common.hashing import stable_text_hash
from vibethinker_experiments.data.decontamination import BenchmarkDenyIndex
from vibethinker_experiments.data.rl import prepare_stdin_stdout_tests


def test_stable_hash_normalizes_unicode_case_and_whitespace() -> None:
    assert stable_text_hash("Ａ  B\nC") == stable_text_hash("a b c")


def test_benchmark_exact_and_substantial_near_match() -> None:
    benchmark = " ".join(f"token{i}" for i in range(30))
    index = BenchmarkDenyIndex.build([("bench:1", benchmark)])
    assert index.match(benchmark.upper()).hard_deny
    near = "prefix " + " ".join(f"token{i}" for i in range(30)) + " suffix"
    result = index.match(near)
    assert result.near_deny
    assert result.near_labels == ("bench:1",)


def test_prepare_tests_joins_lines_deduplicates_and_sorts() -> None:
    tests, error = prepare_stdin_stdout_tests(
        {
            "inputs": [["1", "2"], "1\n2", "3"],
            "outputs": [["3"], "3", "3"],
        }
    )
    assert error is None
    assert tests is not None
    assert set(tests["inputs"]) == {"1\n2", "3"}
    assert len(tests["inputs"]) == len(tests["outputs"]) == 2


def test_prepare_tests_rejects_conflicting_outputs() -> None:
    tests, error = prepare_stdin_stdout_tests(
        {"inputs": ["same", "same"], "outputs": ["one", "two"]}
    )
    assert tests is None
    assert error == "conflicting_test_outputs"
