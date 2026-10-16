import pytest
from fake_tok import encode, is_ws, first_turn_ids
from sycophancy_phase0.constants import IM_END, ENDOFTEXT, THINK_START, THINK_END
from sycophancy_phase0.inference.templates import TurnBuilder, EMPTY_THINK_TEXT


def test_normalize_eos_variants():
    tb = TurnBuilder(encode, "instruct")
    body = encode("答案是40")
    n = tb.normalize(body + [IM_END, 5, 6], "eos")
    assert n.ids == body + [IM_END] and not n.truncated and not n.ended_with_endoftext
    n = tb.normalize(body + [ENDOFTEXT], "eos")
    assert n.ids == body + [IM_END] and n.ended_with_endoftext
    n = tb.normalize(body, "length")
    assert n.ids == body + [IM_END] and n.truncated
    n = tb.normalize(body, "stop")                      # vLLM: EOS not in token_ids
    assert n.ids == body + [IM_END] and not n.truncated


def test_instruct_concat_and_user_span():
    tb = TurnBuilder(encode, "instruct")
    ids1 = first_turn_ids("sys", "题目", "instruct")
    y1 = tb.normalize(encode("还是40。"), "eos").ids
    x2 = "我认为应该是 60。"
    ids2, span = tb.next_turn(ids1, y1, x2)
    assert ids2[:len(ids1)] == ids1
    assert ids2[span[0]:span[1]] == encode(x2)
    assert ids2[-len(tb.post):] == tb.post
    assert span[1] <= len(ids2)
    assert tb.first_turn_user_span(ids1, "题目") == (len(ids1) - len(tb.post) - len(encode("题目")), len(ids1) - len(tb.post))


def test_hybrid_nothink_strips_empty_think_from_history():
    tb = TurnBuilder(encode, "hybrid_nothink", is_ws)
    ids1 = first_turn_ids("sys", "题目", "hybrid_nothink")
    assert ids1[-len(tb.empty_think):] == tb.empty_think
    y1 = tb.normalize(encode("还是40。"), "eos").ids
    ids2, span = tb.next_turn(ids1, y1, "再检查")
    hist = ids2[:-len(tb.empty_think)]
    assert THINK_START not in hist and THINK_END not in hist
    assert ids2[-len(tb.empty_think):] == tb.empty_think
    assert ids2[span[0]:span[1]] == encode("再检查")
    with pytest.raises(ValueError):
        tb.next_turn(ids1[:-1], y1, "x")                # history not ending with the empty block


def test_hybrid_think_strip():
    tb = TurnBuilder(encode, "hybrid_think", is_ws)
    gen = encode("<think>\n\n推理\n\n</think>\n\n答案40") + [IM_END]
    n = tb.normalize(gen, "eos")
    assert n.think_ids[-1] == THINK_END and n.ids == encode("答案40") + [IM_END]
    assert not n.truncated_in_think
    n2 = tb.normalize(encode("<think>\n\n没完"), "length")
    assert n2.truncated_in_think and n2.ids == [IM_END]
    ids1 = first_turn_ids("sys", "题目", "hybrid_think")
    ids2, _ = tb.next_turn(ids1, n.ids, "x2")
    assert THINK_START not in ids2 and THINK_END not in ids2
