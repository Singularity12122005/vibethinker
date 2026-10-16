"""Qwen3 special-token ids and frozen defaults (plan §4.1, §4.3)."""
IM_START = 151644
IM_END = 151645          # primary EOS; every normalised assistant turn ends with it
ENDOFTEXT = 151643       # secondary EOS; also the pad id
THINK_START = 151667
THINK_END = 151668
EOS_IDS = (IM_END, ENDOFTEXT)
PAD_ID = ENDOFTEXT

TEMPERATURE = 0.7        # effective temperature; applied inside SeededGumbelSampler
MAX_NEW_TOKENS = 512
MAX_NEW_TOKENS_THINK = 4096
SYSTEM_PROMPT = "你是一个严谨的数学与程序分析助手。请直接回答问题并给出简要理由。"

ACTION_GRID = (-1.0, -0.5, 0.0, 0.5, 1.0)          # multiples of alpha_max (plan §3)
LAMBDA_DOSE_GRID = (0.0, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0)
LAMBDA_DOSE_PRIMARY = 0.05
Z_LAYERS = (8, 12, 16, 20, 24, 28, 32, 36, 40, 44)  # L = model.model.layers[L] output = hidden_states[L+1]
