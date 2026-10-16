"""Character-level fake tokenizer with Qwen3 special ids, for template tests."""
import re
from sycophancy_phase0.constants import IM_START, IM_END, ENDOFTEXT, THINK_START, THINK_END

SPECIAL = {"<|im_start|>": IM_START, "<|im_end|>": IM_END, "<|endoftext|>": ENDOFTEXT,
           "<think>": THINK_START, "</think>": THINK_END}
_RE = re.compile("|".join(re.escape(k) for k in SPECIAL) + r"|\n\n|.|\n", re.S)


def encode(text: str):
    out = []
    for m in _RE.finditer(text):
        tok = m.group(0)
        if tok in SPECIAL:
            out.append(SPECIAL[tok])
        elif tok == "\n\n":
            out.append(271)            # Qwen's double-newline token
        else:
            out.append(1000 + ord(tok))
    return out


def is_ws(i: int) -> bool:
    """newline-only tokens (the template's lstrip('\\n') semantics)"""
    return i == 271 or i == 1000 + ord("\n")


def first_turn_ids(system: str, x1: str, mode: str):
    text = f"<|im_start|>system\n{system}<|im_end|>\n<|im_start|>user\n{x1}<|im_end|>\n<|im_start|>assistant\n"
    if mode == "hybrid_nothink":
        text += "<think>\n\n</think>\n\n"
    return encode(text)
