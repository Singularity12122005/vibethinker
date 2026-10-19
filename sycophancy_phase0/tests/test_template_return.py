"""Round 13: apply_chat_template return structures (list / dict / BatchEncoding-like UserDict / tensor) all normalise to a list of ids."""
from collections import UserDict
import numpy as np
from sycophancy_phase0.rollout import hf_first_turn_ids, template_ids_to_list


class _Tok:
    def __init__(self, kind):
        self.kind = kind
        self.calls = []
    def apply_chat_template(self, msgs, **kw):
        self.calls.append(kw)
        ids = [5, 6, 7, 8]
        if self.kind == "list":
            return ids
        if self.kind == "dict":
            return {"input_ids": ids, "attention_mask": [1] * 4}
        if self.kind == "userdict":
            return UserDict({"input_ids": ids, "attention_mask": [1] * 4})
        if self.kind == "array":
            return np.array(ids)
        if self.kind == "batched":
            return UserDict({"input_ids": np.array([ids]), "attention_mask": np.ones((1, 4), dtype=int)})
        raise AssertionError(self.kind)


def test_every_return_structure_gives_the_same_ids():
    for kind in ("list", "dict", "userdict", "array", "batched"):
        tok = _Tok(kind)
        f = hf_first_turn_ids(tok, "main", "sys")
        assert f("hello") == [5, 6, 7, 8], kind
        assert tok.calls[-1]["enable_thinking"] is False and tok.calls[-1]["add_generation_prompt"] is True
    assert hf_first_turn_ids(_Tok("list"), "hybrid_think", "sys")("x") == [5, 6, 7, 8]
    assert template_ids_to_list(UserDict({"input_ids": [1, 2]})) == [1, 2] and template_ids_to_list((3, 4)) == [3, 4]
