"""Token-id level multi-turn construction (plan §4.1).

The chat text is never re-tokenised between turns: ``ids_t = base + y_{t-1}_ids + pre + xt + post`` where
``base`` is ``ids_{t-1}`` (``instruct`` / ``hybrid_think``) or ``ids_{t-1}`` minus the trailing empty think block
(``hybrid_nothink``).  ``user_span`` is the absolute interval of the x_t content tokens inside ``ids_t``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

from ..constants import ENDOFTEXT, IM_END, THINK_END, THINK_START

Encode = Callable[[str], List[int]]           # tokenizer.encode(text, add_special_tokens=False)
IsWhitespaceTok = Callable[[int], bool]       # True if the token decodes to whitespace/newlines only

PRE_TEXT = "\n<|im_start|>user\n"
POST_TEXT = "<|im_end|>\n<|im_start|>assistant\n"
EMPTY_THINK_TEXT = "<think>\n\n</think>\n\n"

MODES = ("instruct", "hybrid_nothink", "hybrid_think")


@dataclass
class NormalizedTurn:
    ids: List[int]                 # ends with IM_END
    think_ids: Optional[List[int]] # hybrid_think only: ids up to and including THINK_END
    finish_reason: str
    truncated: bool
    truncated_in_think: bool
    ended_with_endoftext: bool


class TurnBuilder:
    def __init__(self, encode: Encode, mode: str, is_whitespace_tok: Optional[IsWhitespaceTok] = None):
        if mode not in MODES:
            raise ValueError(mode)
        self.encode = encode
        self.mode = mode
        self.is_ws = is_whitespace_tok or (lambda _i: False)
        self.pre = encode(PRE_TEXT)
        self.post = encode(POST_TEXT)
        self.empty_think = encode(EMPTY_THINK_TEXT) if mode == "hybrid_nothink" else []

    # ------------------------------------------------------------------ EOS normalisation
    def normalize(self, gen_ids: Sequence[int], finish_reason: str) -> NormalizedTurn:
        ids = list(gen_ids)
        cut = next((i for i, t in enumerate(ids) if t in (IM_END, ENDOFTEXT)), None)
        ended_with_endoftext = False
        truncated = False
        if cut is not None:
            ended_with_endoftext = ids[cut] == ENDOFTEXT
            ids = ids[:cut] + [IM_END]
        else:
            if finish_reason == "length":
                truncated = True
            ids = ids + [IM_END]
        think_ids = None
        truncated_in_think = False
        if self.mode == "hybrid_think":
            ids, think_ids, truncated_in_think = self._strip_think(ids)
        if THINK_START in ids or THINK_END in ids:
            raise ValueError("think tokens left in normalised assistant ids")
        return NormalizedTurn(ids, think_ids, finish_reason, truncated, truncated_in_think, ended_with_endoftext)

    def _strip_think(self, ids: List[int]) -> Tuple[List[int], Optional[List[int]], bool]:
        if THINK_END not in ids:
            # no closing tag: whole output is reasoning; keep only the EOS so the history stays well-formed
            return [IM_END], ids[:-1], True
        k = ids.index(THINK_END)
        think = ids[: k + 1]
        rest = ids[k + 1:]
        while rest and rest[0] != IM_END and self.is_ws(rest[0]):   # template: content.split('</think>')[-1].lstrip('\n')
            rest = rest[1:]
        return rest, think, False

    # ------------------------------------------------------------------ next turn
    def next_turn(self, ids_prev: Sequence[int], assistant_ids: Sequence[int], x_t: str) -> Tuple[List[int], Tuple[int, int]]:
        """Return (ids_t, user_span). ``assistant_ids`` must be normalised (ends with IM_END)."""
        if not assistant_ids or assistant_ids[-1] != IM_END:
            raise ValueError("assistant_ids must be normalised (end with <|im_end|>)")
        base = list(ids_prev)
        if self.mode == "hybrid_nothink":
            n = len(self.empty_think)
            if base[-n:] != self.empty_think:
                raise ValueError("hybrid_nothink: previous ids must end with the empty think block")
            base = base[:-n]
        xt = self.encode(x_t)
        start = len(base) + len(assistant_ids) + len(self.pre)
        ids_t = base + list(assistant_ids) + self.pre + xt + self.post + self.empty_think
        return ids_t, (start, start + len(xt))

    def first_turn_user_span(self, ids_1: Sequence[int], x_1: str) -> Tuple[int, int]:
        """Locate x_1 inside the templated first-turn ids (last occurrence of encode(x_1))."""
        xt = self.encode(x_1)
        ids = list(ids_1)
        n = len(xt)
        for s in range(len(ids) - n, -1, -1):
            if ids[s:s + n] == xt:
                return (s, s + n)
        raise ValueError("x_1 tokens not found in ids_1 (tokenisation boundary effect)")
