from __future__ import annotations

from vibethinker_experiments.evaluation.core import (
    context_limit_hit_score,
    score_completion,
)
from vibethinker_experiments.evaluation.graders import (
    UNSAFE_CODE_GRADER_WARNING,
    unsafe_python_assert_grader,
)


def test_context_limit_uses_128k_profile_value():
    assert context_limit_hit_score(120_000, 11_072, context_tokens=131_072) == 1.0
    assert context_limit_hit_score(64_000, 1_536, context_tokens=131_072) == 0.0


def test_pure_scoring_preserves_generation_input(toy_rows, generation_results, toy_profile):
    panel = {row["panel_id"]: row for row in toy_rows}
    generation = generation_results[0]
    original = dict(generation)
    scored = score_completion(
        panel[generation["panel_id"]],
        generation,
        context_tokens=toy_profile.context_tokens,
    )
    assert scored["end_to_end_score"] == 1.0
    assert generation == original
    assert "raw_completion" not in scored


def test_code_grader_is_opt_in_and_warns(toy_rows, generation_results, toy_profile):
    panel = {row["panel_id"]: row for row in toy_rows}
    generation = next(row for row in generation_results if row["domain"] == "code")
    without_executor = score_completion(
        panel[generation["panel_id"]],
        generation,
        context_tokens=toy_profile.context_tokens,
    )
    with_executor = score_completion(
        panel[generation["panel_id"]],
        generation,
        context_tokens=toy_profile.context_tokens,
        code_grader=unsafe_python_assert_grader,
    )
    assert without_executor["capability_score"] == 0.0
    assert with_executor["capability_score"] == 1.0
    assert with_executor["capability_detail"]["security_warning"] == UNSAFE_CODE_GRADER_WARNING
