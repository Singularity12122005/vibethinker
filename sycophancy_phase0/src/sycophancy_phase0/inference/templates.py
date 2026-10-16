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
IsNewlineTok = Callable[[int], bool]          # True iff the token decodes to newlines only (template: lstrip('\n'))

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
    truncated_in_think: bool       # no </think> AND cut by max_new_tokens
    ended_with_endoftext: bool
    no_think_close: bool = False   # hybrid_think: no </think> in the output (by length or by an early EOS)
    stray_think_tokens: bool = False  # non-think mode emitted <think>/</think>; they were dropped from ids


class TurnBuilder:
    def __init__(self, encode: Encode, mode: str, is_newline_tok: Optional[IsNewlineTok] = None):
        if mode not in MODES:
            raise ValueError(mode)
        self.encode = encode
        self.mode = mode
        self.is_nl = is_newline_tok or (lambda _i: False)
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
        no_think_close = False
        stray = False
        if self.mode == "hybrid_think":
            ids, think_ids, no_think_close = self._strip_think(ids)
            truncated_in_think = no_think_close and truncated
        if THINK_START in ids or THINK_END in ids:
            # stray think tokens in a non-think mode (or nested tags): drop them, flag the turn, keep the run going
            stray = True
            ids = [t for t in ids if t not in (THINK_START, THINK_END)]
        return NormalizedTurn(ids, think_ids, finish_reason, truncated, truncated_in_think, ended_with_endoftext,
                              no_think_close, stray)

    def _strip_think(self, ids: List[int]) -> Tuple[List[int], Optional[List[int]], bool]:
        """Returns (content ids ending in IM_END, think ids incl. </think>, no_think_close)."""
        if THINK_END not in ids:
            # no closing tag: the whole output is reasoning; keep only the EOS so the history stays well-formed
            return [IM_END], ids[:-1], True
        k = ids.index(THINK_END)
        think = ids[: k + 1]
        rest = ids[k + 1:]
        while rest and rest[0] != IM_END and self.is_nl(rest[0]):   # template: content.split('</think>')[-1].lstrip('\n')
            rest = rest[1:]
        return rest, think, False

    # ------------------------------------------------------------------ next turn
    def next_turn(self, ids_prev: Sequence[int], assistant_ids: Sequence[int], x_t: str) -> Tuple[List[int], Tuple[int, int]]:
        """Return (ids_t, user_span). ``assistant_ids`` must be normalised (ends with IM_END)."""
        ids_t, user_span, _ = self.next_turn_ex(ids_prev, assistant_ids, x_t)
        return ids_t, user_span

    def next_turn_ex(self, ids_prev: Sequence[int], assistant_ids: Sequence[int], x_t: str
                     ) -> Tuple[List[int], Tuple[int, int], Tuple[int, int]]:
        """Return (ids_t, user_span, prev_assistant_span).

        ``prev_assistant_span`` is the absolute interval of the y_{t-1} *content* tokens inside ``ids_t``
        (the closing <|im_end|> is a template token and is excluded) — the R3 pooling set of plan §4.5.
        """
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
        prev_span = (len(base), len(base) + len(assistant_ids) - 1)
        return ids_t, (start, start + len(xt)), prev_span

    def first_turn_user_span(self, ids_1: Sequence[int], x_1: str) -> Tuple[int, int]:
        """Locate x_1 inside the templated first-turn ids: last occurrence of encode(x_1) *before* the trailing
        generation prompt (post [+ empty think block])."""
        xt = self.encode(x_1)
        ids = list(ids_1)
        n = len(xt)
        tail = len(self.post) + len(self.empty_think)
        for s in range(len(ids) - tail - n, -1, -1):
            if ids[s:s + n] == xt:
                return (s, s + n)
        raise ValueError("x_1 tokens not found in ids_1 (tokenisation boundary effect)")
