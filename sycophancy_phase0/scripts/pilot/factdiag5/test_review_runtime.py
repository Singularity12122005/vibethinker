"""串行评审与独立协议的处理器测试，仅使用合成回答。"""
from contextlib import nullcontext, redirect_stdout
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace
import io
import json
import unittest

from . import review_runtime
from .judge_core import RECOMMENDED_ATOMIC_SCOPE, build_inputs, pending_inputs
from .review_protocol import GENERATION_COMMIT, REVIEW_ORDER, RUN_SETTINGS
from .test_judge_core import synthetic


COMMIT = "b" * 40


def payload():
    material, rows, prereg, protocol, relation = synthetic()
    return build_inputs(material, rows, prereg, approved_atomic_scope=RECOMMENDED_ATOMIC_SCOPE,
                        relation_protocol=protocol, relation_materials=relation)


def fake_outputs(prompts, limit):
    raw = json.dumps(dict(mention="ABSENT", claims=[], parse_status="OK")) if limit == 2048 else "not a valid label"
    return [dict(raw="YES" if "Answer with exactly one word: YES or NO." in p else raw,
                 judge_truncated=False, n_new_tokens=8) for p in prompts]


class ReviewRuntimeTests(unittest.TestCase):
    def test_generation_call_preserves_old_parameters_and_detects_truncation(self):
        import numpy as np
        calls = []
        class Batch(dict):
            def __init__(self):
                super().__init__(input_ids=np.array([[1, 2, 3], [1, 2, 3]]))
                self.input_ids = self["input_ids"]
            def to(self, device):
                self.device = device
                return self
        class Tokenizer:
            eos_token_id, pad_token_id = 9, 0
            def apply_chat_template(self, messages, **kwargs):
                self.last_template_kwargs = kwargs
                return messages[0]["content"]
            def __call__(self, rendered, **kwargs):
                self.last_tokenizer_kwargs = kwargs
                return Batch()
            def batch_decode(self, sampled, **kwargs):
                self.last_decode_kwargs = kwargs
                return ["YES", "unfinished"]
        def generate(**kwargs):
            calls.append(kwargs)
            return np.array([[1, 2, 3, 7, 9, 0], [1, 2, 3, 8, 8, 8]])
        tokenizer = Tokenizer()
        client = SimpleNamespace(tok=tokenizer, torch=SimpleNamespace(no_grad=nullcontext),
                                 model=SimpleNamespace(device="cpu", generate=generate))
        returned = review_runtime.infer_once(client, ["a", "b"], 3)
        self.assertEqual(tokenizer.last_template_kwargs, dict(tokenize=False, add_generation_prompt=True))
        self.assertEqual(tokenizer.last_tokenizer_kwargs, dict(return_tensors="pt", padding=True))
        self.assertEqual(tokenizer.last_decode_kwargs, dict(skip_special_tokens=True))
        self.assertEqual({k: v for k, v in calls[0].items() if k != "input_ids"},
                         dict(do_sample=False, max_new_tokens=3, pad_token_id=0,
                              temperature=None, top_p=None, top_k=None))
        self.assertFalse(returned[0]["judge_truncated"])
        self.assertEqual(returned[0]["n_new_tokens"], 2)
        self.assertTrue(returned[1]["judge_truncated"])

    def test_parameters_equal_old_sources_and_atomic_protocol(self):
        self.assertEqual(RUN_SETTINGS["batch"], 8)
        self.assertFalse(RUN_SETTINGS["do_sample"])
        self.assertEqual(RUN_SETTINGS["padding_side"], "left")
        self.assertEqual(RUN_SETTINGS["max_new_tokens"], dict(legacy_stance=64,
            legacy_propositions=512, evidence_disputed=64, relations_v2=2048))
        self.assertTrue(all(RUN_SETTINGS[k] is None for k in ("temperature", "top_p", "top_k")))

    def test_serial_order_once_and_failed_parsing_not_retried(self):
        p = payload()
        saved = dict(legacy={}, relations={})
        calls, writes = [], []
        def call(prompts, limit):
            calls.append(limit)
            self.assertTrue(writes)
            return fake_outputs(prompts, limit)
        def write(storage, records):
            writes.append((storage, deepcopy(records)))
        with redirect_stdout(io.StringIO()):
            summary = review_runtime.serial_review(p, saved, RUN_SETTINGS, COMMIT, call, write)
        expected = []
        for kind in REVIEW_ORDER:
            expected.extend([RUN_SETTINGS["max_new_tokens"][kind]] * ((len(p["queues"][kind]) + 7) // 8))
        self.assertEqual(calls, expected)
        self.assertEqual(summary["legacy"]["attempted"], sum(len(p["queues"][kind]) for kind in REVIEW_ORDER[:-1]))
        self.assertGreater(summary["legacy"]["missing"], 0)
        self.assertTrue(all(r["attempts"] == 1 for records in saved.values() for r in records.values()))
        before = list(calls)
        with redirect_stdout(io.StringIO()):
            review_runtime.serial_review(p, saved, RUN_SETTINGS, COMMIT, call, write)
        self.assertEqual(calls, before)

    def test_interrupted_dispatch_stays_missing_without_second_model_call(self):
        p = payload()
        saved = dict(legacy={}, relations={})
        writes = []
        def fail(prompts, limit):
            raise RuntimeError("合成中断")
        with self.assertRaisesRegex(RuntimeError, "合成中断"):
            review_runtime.serial_review(p, saved, RUN_SETTINGS, COMMIT, fail,
                                        lambda store, values: writes.append((store, deepcopy(values))))
        attempted = set(saved["legacy"])
        self.assertEqual(len(attempted), 8)
        self.assertEqual(set(writes[-1][1]), attempted)
        self.assertTrue(all(r["result"]["missing"] for r in saved["legacy"].values()))
        pending = pending_inputs(p["queues"]["legacy_stance"], saved["legacy"])
        self.assertFalse(attempted & {q["id"] for q in pending})
        with redirect_stdout(io.StringIO()):
            summary = review_runtime.serial_review(p, saved, RUN_SETTINGS, COMMIT, fake_outputs, lambda *a: None)
        self.assertEqual(summary["legacy"]["result_not_saved"], 8)

    def test_completed_return_cannot_be_replaced(self):
        q = payload()["queues"]["legacy_stance"][0]
        saved = review_runtime.reserve_once({}, [q], COMMIT)
        saved[q["id"]] = review_runtime.finish_once(saved, q, dict(raw="bad", judge_truncated=False))
        with self.assertRaises(ValueError):
            review_runtime.finish_once(saved, q, dict(raw="changed", judge_truncated=False))

    def test_wrong_return_count_preserves_dispatch_as_missing(self):
        p = payload()
        saved = dict(legacy={}, relations={})
        with self.assertRaisesRegex(RuntimeError, "返回条数"):
            review_runtime.serial_review(p, saved, RUN_SETTINGS, COMMIT, lambda *a: [], lambda *a: None)
        self.assertEqual(len(saved["legacy"]), 8)
        self.assertTrue(all(r["completion"] == "attempted_result_missing" for r in saved["legacy"].values()))

    def test_gpu_busy_and_check_only_never_load_client(self):
        p = payload()
        protocol = dict(counts=p["counts"], runtime=RUN_SETTINGS)
        with TemporaryDirectory() as folder:
            out = Path(folder)
            with patch.object(review_runtime, "assert_remote"), \
                    patch.object(review_runtime, "validate_review", return_value=protocol), \
                    patch.object(review_runtime, "validate_generation"), \
                    patch.object(review_runtime, "review_lock", side_effect=lambda _: nullcontext()), \
                    patch.object(review_runtime, "prepare_remote_inputs", return_value=p), \
                    patch.object(review_runtime.subprocess, "check_output", return_value="1234") as check, \
                    patch.object(review_runtime, "load_client") as client, redirect_stdout(io.StringIO()):
                review_runtime.run(out, out, COMMIT, check_only=True)
                check.assert_not_called()
                client.assert_not_called()
                with self.assertRaisesRegex(RuntimeError, "现有进程"):
                    review_runtime.run(out, out, COMMIT)
                client.assert_not_called()

    def test_unfrozen_review_stops_before_loading_inputs_or_model(self):
        with patch.object(review_runtime, "assert_remote"), \
                patch.object(review_runtime, "validate_review", side_effect=ValueError("评审尚未冻结")), \
                patch.object(review_runtime, "prepare_remote_inputs") as inputs, \
                patch.object(review_runtime, "load_client") as client:
            with self.assertRaises(ValueError):
                review_runtime.run(Path("."), Path("."), GENERATION_COMMIT)
            inputs.assert_not_called()
            client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
