"""正式入口的处理器测试：合成返回值，不载入模型、不访问GPU或远端。"""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import base64
import contextlib
import hashlib
import io
import math
import sys
import unittest

from . import runtime
from .freeze import validate, sha256
from .planning import score_requests
from .prepare import reject_raw, save
from .test_planning import Engine, fixture, plan
from .version_scores import build_version_scores


COMMIT = "a" * 40


def completed(request, **extra):
    return dict(request, assistant_ids=[1], assistant_text="合成结果", prompt_ids=[1], parsed={},
                n_new_tokens=20, truncated=False, looped=False, freeze_commit=COMMIT, **extra)


class RuntimeTests(unittest.TestCase):
    def test_remote_confidence_signature_and_return_are_used(self):
        calls = []
        def actual(model, seqs, suffix_ids, top_k=50, pad_id=None, temperature=.7):
            calls.append(dict(temperature=temperature, top_k=top_k, pad_id=pad_id, suffix_ids=suffix_ids))
            return dict(suffix_logp=[[-1000.25, -1001.75]], top_logits=[], top_ids=[])
        inputs = dict(seqs=[[1, 2]], suffixes=[[[3, 4], [5, 6, 7]]], temperature=1.)
        self.assertEqual(runtime.confidence_raw(actual, None, inputs, 0), [[-1000.25, -1001.75]])
        self.assertEqual(calls[0]["temperature"], 1.)
        self.assertEqual(calls[0]["suffix_ids"], inputs["suffixes"])
        def older(model, seqs, suffix_ids, top_k=50, pad_id=None):
            raise AssertionError("不得调用未核实的接口")
        with self.assertRaises(RuntimeError):
            runtime.confidence_raw(older, None, inputs, 0)

    def test_confidence_missing_or_nonfinite_is_blocked(self):
        inputs = dict(seqs=[[1]], suffixes=[[[2], [3]]], temperature=1.)
        for bad in ([], [[0]], [[0, math.nan]]):
            def actual(model, seqs, suffix_ids, top_k=50, pad_id=None, temperature=.7):
                return dict(suffix_logp=bad)
            with self.assertRaises(RuntimeError):
                runtime.confidence_raw(actual, None, inputs, None)

    def test_completed_requests_cannot_silently_change_or_duplicate(self):
        requests = plan()["requests"][:2]
        rows = [completed(requests[0])]
        self.assertEqual(len(runtime.cached_rows(rows, requests, COMMIT)), 1)
        for changed in (dict(rows[0], seed=7), dict(rows[0], candidate="不同"),
                        dict(rows[0], n_new_tokens=None), dict(rows[0], freeze_commit="b" * 40)):
            with self.assertRaises(RuntimeError):
                runtime.cached_rows([changed], requests, COMMIT)
        with self.assertRaises(RuntimeError):
            runtime.cached_rows(rows + rows, requests, COMMIT)

    def test_score_cache_checks_definition_and_shape(self):
        definition = plan()["scoring_requests"][0]
        row = dict(score_id=definition["score_id"], definition=definition, full_name_logp=[-1., -5.], freeze_commit=COMMIT)
        self.assertEqual(len(runtime.cached_scores([row], [definition], COMMIT)), 1)
        with self.assertRaises(RuntimeError):
            runtime.cached_scores([dict(row, full_name_logp=[-1.])], [definition], COMMIT)

    def test_later_phase_is_blocked_if_clean_forward_missing(self):
        p = plan()
        clean = {r["request_id"]: completed(r) for r in p["requests"] if r["cell"] == "R1prime"}
        historical = next(r for r in p["requests"] if r["cell"] == "R2")
        clean[historical["request_id"]] = completed(historical)
        with self.assertRaises(RuntimeError):
            runtime.validate_sequence(clean, {}, {}, p["requests"], p["scoring_requests"], [])

    def test_old_parser_identity_status_and_complete_text(self):
        old = runtime.previous()
        hs, materials, _ = fixture()
        p = plan()
        for m in materials.values():
            for key in ("R", "F"):
                m[key].update(answer_format="entity", d=m["R"]["gold"] if key == "F" else m["F"]["gold"])
        task = next(r for r in p["requests"] if r["cell"] == "5.5" and r["unit"] == "F-D")
        task = dict(task, original="Mistaken Person", candidate="True Translator")
        materials[task["work_id"]]["F"]["gold"] = "True Translator"
        text = "正文保留供后续独立评审。\nFinal answer: " + task["candidate"] + " | Status: CANNOT_VERIFY"
        parsed, status = runtime.parse_answer(text, task, materials[task["work_id"]], [], old)
        self.assertEqual(parsed["answer_identity"], "d")
        self.assertTrue(parsed["correct"])
        self.assertEqual(status["status"], "CANNOT_VERIFY")
        parsed, status = runtime.parse_answer(text.replace("CANNOT_VERIFY", "UNKNOWN"), task, materials[task["work_id"]], [], old)
        self.assertEqual(parsed["answer_identity"], "d")
        self.assertTrue(status["missing"])
        ordinary = dict(task, cell="R3")
        parsed, _ = runtime.parse_answer("Final answer: Unrelated Person", ordinary, materials[task["work_id"]], [], old)
        self.assertEqual(parsed["answer_identity"], "other")
        parsed, _ = runtime.parse_answer("Final answer: " + task["original"], ordinary, materials[task["work_id"]], [], old)
        self.assertEqual(parsed["answer_identity"], "x")
        self.assertFalse(parsed["correct"])

    def test_budget_uses_shared_total_and_actual_fifth_mean(self):
        p = plan()
        cache = {r["request_id"]: completed(r) for r in p["requests"] if r["stage"] == "5.1"}
        budget = SimpleNamespace(used_tokens=lambda _: dict(total=100000, files={}))
        with contextlib.redirect_stdout(io.StringIO()):
            report = runtime.budget_checkpoint(Path("."), cache, p["requests"], budget)
        self.assertEqual(report["observed_5_1_mean"], 20)
        self.assertEqual(report["projected_fifth_completion"], 100000 + 2308 * 20)
        budget.used_tokens = lambda _: dict(total=1490000, files={})
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
            runtime.budget_checkpoint(Path("."), cache, p["requests"], budget)

    def test_loop_limit_is_per_cell_and_arm_and_truncation_is_reported(self):
        p = plan()
        rows = [completed(r) for r in p["requests"][:20]]
        rows[0]["truncated"] = rows[1]["truncated"] = True
        self.assertTrue(runtime.diagnostic(rows)[0]["truncation_exceeds_5pct"])
        rows[0]["looped"] = rows[1]["looped"] = True
        with self.assertRaises(RuntimeError):
            runtime.diagnostic(rows)

    def test_public_output_rejects_raw_history(self):
        reject_raw(dict(histories=[dict(history_id="合成", current_answer="已知姓名")]))
        with self.assertRaises(ValueError):
            reject_raw(dict(histories=[dict(assistant_text="不得落入公开材料")]))
        with self.assertRaises(RuntimeError):
            runtime.assert_remote(Path("."), Path("."))

    def test_runtime_freeze_checks_material_and_code_without_proof_files(self):
        with TemporaryDirectory() as folder:
            out = Path(folder)
            path = out / "data.json"
            path.write_text('{"safe":true}\n', encoding="utf-8")
            reg = dict(analysis_freeze=dict(status="frozen"), stage1_confirmed=True,
                step0_complete=True, step0_commit="b" * 40,
                frozen_files={"data.json": sha256(path)}, code_sha256={})
            save(out / "factdiag5_prereg.json", reg)
            self.assertEqual(validate(out, out, COMMIT), reg)
            path.write_text('{"safe":false}\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                validate(out, out, COMMIT)

    def test_runtime_refuses_before_loading_model(self):
        # 未冻结、占用和本地目录各自的拦截路径不应构造主模型。
        with TemporaryDirectory() as folder:
            with patch.object(runtime, "assert_remote"), patch.object(runtime, "runtime_lock", return_value=contextlib.nullcontext()), \
                    patch.object(runtime, "validate", side_effect=ValueError("未冻结")), patch.object(runtime, "previous") as old:
                with self.assertRaisesRegex(ValueError, "未冻结"):
                    runtime.run(Path(folder), Path(folder), COMMIT)
                old.assert_not_called()

    def test_runtime_order_budget_and_resume_without_duplicate_generation(self):
        hs, materials, sources = fixture()
        full = plan()
        chosen = [next(r for r in full["requests"] if r["cell"] == cell)
                  for cell in ("R1prime", "R2", "R3", "F-E-true", "F-E-sys", "M-wrong", "M-right", "E-inapp", "E-false", "5.5")]
        small = dict(full, requests=chosen, scoring_requests=score_requests(chosen))
        versions = build_version_scores(materials, full["histories"])
        payload = dict(plan=small, materials=list(materials.values()), version_scores=versions,
                       registered_people={key: [] for key in materials})
        engine = Engine()
        engine.tok.pad_token_id = None
        engine.model = None
        calls = []
        def fake_confidence(model, seqs, suffix_ids, top_k=50, pad_id=None, temperature=.7):
            calls.append("score")
            return dict(suffix_logp=[[-float(j + 1) for j in range(len(suffix_ids[0]))]])
        def fake_generate(engine, tasks, bank, people, old, commit):
            calls.append(tasks[0]["cell"])
            return [dict(r, assistant_ids=[1], assistant_text="合成输出", n_new_tokens=20,
                         parsed={}, truncated=False, looped=False, freeze_commit=commit) for r in tasks]
        fake_old = SimpleNamespace(p3=SimpleNamespace(previous_runtime=SimpleNamespace(Main=lambda *a, **k: engine)))
        budget = SimpleNamespace(used_tokens=lambda _: dict(total=100, files={}),
                                 check_next_batch=lambda *a: calls.append("budget"))
        with TemporaryDirectory() as folder:
            out = Path(folder)
            save(out / "factdiag5_materials.json", payload)
            with patch.object(runtime, "assert_remote"), patch.object(runtime, "runtime_lock", side_effect=lambda _: contextlib.nullcontext()), \
                    patch.object(runtime, "validate", return_value=dict(order=list(runtime.ORDER))), \
                    patch.object(runtime, "previous", return_value=fake_old), \
                    patch.object(runtime, "source_histories", return_value=sources), \
                    patch.object(runtime, "parse_answer"), patch.object(runtime, "shared_budget", return_value=budget), \
                    patch.object(runtime.subprocess, "check_output", return_value="") as gpu, \
                    patch.object(runtime, "generate_batch", side_effect=fake_generate) as generate, \
                    patch.dict(sys.modules, {"sycophancy_phase0.inference.hf_engine": SimpleNamespace(confidence_features=fake_confidence)}), \
                    contextlib.redirect_stdout(io.StringIO()):
                runtime.run(out, out, COMMIT)
                self.assertEqual(generate.call_count, 10)
                self.assertEqual(calls.count("score"), 33)
                self.assertEqual(calls[calls.index("R1prime") + 1:calls.index("R2") - 1], ["score"] * 31)
                self.assertLess(calls.index("R3"), calls.index("F-E-true"))
                self.assertEqual(calls[-1], "5.5")
                # 已完成时既不查询GPU，也不载入模型或重复请求。
                runtime.run(out, out, COMMIT)
                self.assertEqual(generate.call_count, 10)
                self.assertEqual(gpu.call_count, 1)


if __name__ == "__main__":
    unittest.main()
