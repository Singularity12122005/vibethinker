"""VERL reward manager forwarding exact rollout length and truncation metadata."""

from __future__ import annotations

import inspect
import os
from collections import defaultdict
from typing import Any

import torch
from verl.experimental.reward_loop.reward_manager.base import RewardManagerBase
from verl.utils.ray_utils import get_event_loop


class VibeThinkerMathRewardManager(RewardManagerBase):
    def __init__(
        self,
        tokenizer,
        num_examine: int = 0,
        compute_score=None,
        reward_fn_key: str = "data_source",
        config=None,
        **_: Any,
    ) -> None:
        if compute_score is None:
            raise ValueError("VibeThinkerMathRewardManager requires custom compute_score")
        if config is not None:
            super().__init__(config=config, tokenizer=tokenizer, compute_score=compute_score)
        else:
            self.config = None
            self.tokenizer = tokenizer
            self.compute_score = compute_score
            self.loop = get_event_loop()
        self.num_examine = num_examine
        self.reward_fn_key = reward_fn_key
        self.is_async_reward_score = inspect.iscoroutinefunction(compute_score)
        configured = config.get("data", {}).get("max_response_length") if config else None
        self.max_completion_tokens = int(
            configured or os.environ.get("VT_MAX_COMPLETION_TOKENS", "0")
        )
        if self.max_completion_tokens <= 0:
            raise ValueError("max response length is required to detect hard truncation")

    def _score_inputs(self, item):
        prompt_ids = item.batch["prompts"]
        prompt_length = prompt_ids.shape[-1]
        valid_prompt_length = int(item.batch["attention_mask"][:prompt_length].sum().item())
        response_ids = item.batch["responses"]
        valid_response_length = int(item.batch["attention_mask"][prompt_length:].sum().item())
        prompt = self.tokenizer.decode(prompt_ids[-valid_prompt_length:], skip_special_tokens=True)
        response = self.tokenizer.decode(
            response_ids[:valid_response_length], skip_special_tokens=True
        )
        extra_info = dict(item.non_tensor_batch.get("extra_info", {}))
        extra_info.update(
            completion_tokens=valid_response_length,
            hard_truncated=valid_response_length >= self.max_completion_tokens,
            rl_component=extra_info.get("rl_component"),
        )
        return (
            prompt,
            response,
            item.non_tensor_batch["reward_model"]["ground_truth"],
            item.non_tensor_batch[self.reward_fn_key],
            extra_info,
            valid_response_length,
        )

    async def run_single(self, data) -> dict[str, Any]:
        item = data[-1:][0]
        _, response, ground_truth, source, extra, _ = await self.loop.run_in_executor(
            None, self._score_inputs, item
        )
        kwargs = dict(
            data_source=source,
            solution_str=response,
            ground_truth=ground_truth,
            extra_info=extra,
        )
        if self.is_async_reward_score:
            result = await self.compute_score(**kwargs)
        else:
            result = await self.loop.run_in_executor(None, lambda: self.compute_score(**kwargs))
        if isinstance(result, dict):
            return {
                "reward_score": float(result["score"]),
                "reward_extra_info": dict(result),
            }
        return {"reward_score": float(result), "reward_extra_info": {"acc": float(result)}}

    def __call__(self, data, return_dict: bool = False):
        if "rm_scores" in data.batch:
            if return_dict:
                keys = data.meta_info.get("reward_extra_keys", [])
                return {
                    "reward_tensor": data.batch["rm_scores"],
                    "reward_extra_info": {key: data.non_tensor_batch[key] for key in keys},
                }
            return data.batch["rm_scores"]

        rewards = torch.zeros_like(data.batch["responses"], dtype=torch.float32)
        extra_outputs = defaultdict(list)
        for index in range(len(data)):
            item = data[index]
            prompt, response, ground_truth, source, extra, response_length = self._score_inputs(
                item
            )
            result = self.compute_score(
                data_source=source,
                solution_str=response,
                ground_truth=ground_truth,
                extra_info=extra,
            )
            score = result["score"] if isinstance(result, dict) else result
            rewards[index, max(response_length - 1, 0)] = score
            if isinstance(result, dict):
                for key, value in result.items():
                    extra_outputs[key].append(value)
            if index < self.num_examine:
                print(
                    "[reward_sample]",
                    {
                        "prompt": prompt,
                        "response": response,
                        "ground_truth": ground_truth,
                        "completion_tokens": response_length,
                        "score": result,
                    },
                    flush=True,
                )
        if return_dict:
            return {"reward_tensor": rewards, "reward_extra_info": extra_outputs}
        return rewards
