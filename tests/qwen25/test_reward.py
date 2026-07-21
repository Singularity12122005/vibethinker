from vibethinker_experiments.qwen25.verl_reward import score_math_completion


def score(text: str, *, tokens: int = 100):
    return score_math_completion(text, "42", completion_tokens=tokens)


def test_protocol_progress_ladder():
    assert score("plain")["score"] == 0.0
    assert score("<think>x")["score"] == 0.1
    assert score("x</think>")["score"] == 0.1
    assert score("<think>x</think>")["score"] == 0.3


def test_correct_and_wrong_answers():
    assert score("<think>reason</think>42")["binary_success"] == 1.0
    wrong = score("<think>reason</think>41")
    assert wrong["binary_success"] == 0.0
    assert wrong["score"] == 0.3


def test_hard_limit_zeroes_even_correct_answer():
    result = score("<think>reason</think>42", tokens=64768)
    assert result["answer_correct"] == 1.0
    assert result["binary_success"] == 0.0
    assert result["score"] == 0.0


def test_explicit_final_answer_has_precedence():
    result = score("<think>reason</think>The answer is 42.\nFinal answer: 41")
    assert result["answer_correct"] == 0.0
    assert result["score"] == 0.3
