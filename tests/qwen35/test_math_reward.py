from __future__ import annotations

from vibethinker_experiments.qwen35.math_protocol import grade_math_answer, parse_protocol
from vibethinker_experiments.qwen35.verl_reward import score_math_completion


def score(text: str, answer: str = "42", tokens: int = 100):
    return score_math_completion(
        text,
        answer,
        completion_tokens=tokens,
        max_completion_tokens=64768,
        length_soft_start_tokens=32768,
    )


def test_protocol_ladder_and_correct_answer():
    assert score("plain")["score"] == 0
    assert score("<think>x")["score"] == 0.1
    assert score("x</think>")["score"] == 0.1
    assert score("<think>x</think>")["score"] == 0.3
    assert score("<think>reason</think>42")["score"] == 1
    assert parse_protocol("<think>reason</think>42")["format_ok"]


def test_explicit_wrong_conclusion_beats_historical_value():
    result = score("<think>reason</think>The answer is 42.\nFinal answer: 41")
    assert result["score"] == 0.3
    assert result["answer_correct"] == 0


def test_natural_currency_duration_and_requested_quantity():
    assert score("<think>x</think>Michael spends **$4,200**.", "4200")["score"] == 1
    assert score("<think>x</think>The trip takes **4 hours and 15 minutes**.", "255")["score"] == 1
    assert (
        score("<think>x</think>Answer: **42 trucks** are needed for 80 flagstones.")["score"] == 1
    )


def test_fraction_numerator_and_negated_value_do_not_match():
    assert (
        score("<think>x</think>The answer is $\\frac{125}{3}$ roses.", "125")["answer_correct"] == 0
    )
    assert score("<think>x</think>The answer is not 42 but 41.")["answer_correct"] == 0


def test_hard_truncation_keeps_correctness_floor():
    result = score("<think>x</think>42", tokens=64768)
    assert result["score"] == 0.5
    assert result["truncated"] == 1


def test_boxed_parser_handles_nested_fraction():
    passed, detail = grade_math_answer(r"\boxed{\frac{1}{2}}", r"\frac{1}{2}")
    assert passed, detail
