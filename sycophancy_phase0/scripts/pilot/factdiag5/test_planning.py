"""使用合成历史验证规划与门槛，不访问模型或真实对话原文。"""
from collections import Counter
import math
import unittest

from .planning import (PlanBlocked, build_plan, digest, identity, normalize_logprobs,
                       parse_status, seed_for)
from .runtime_adapter import (bind_requests, execution_blockers, generation_arguments,
                              teacher_forcing_inputs, version_teacher_forcing_inputs)
from .templates import CORE, LEGACY, LEGACY_SHA256, validate_legacy
from .version_scores import build_version_scores


def fixture():
    materials, histories, sources = {}, [], {}
    for w in range(10):
        wid = f"R-{w + 1:03d}"
        author, translator, other = f"Author {w}", f"Translator {w}", f"Other {w}"
        materials[wid] = dict(work_id=wid, title=f"Title {w}", ebook=str(1000+w),
            R=dict(conflict_id=wid, gold=author, d=translator, question_en=f"Who wrote Title {w}?"),
            F=dict(conflict_id=f"F-{w+1:03d}", gold=translator, question_en=f"Who translated edition {w}?"),
            d_T=other, E_prime=f"Publisher {w}, 1900", version_control_applicable=True,
            evidence_gate=dict(status="verified", catalog_contributors_checked=True,
                title_page_credits_checked=True, catalog_author_verified=True,
                completeness_verified=True, catalog_source="catalog", catalog_location="contributors",
                title_page_source="ebook", title_page_location="title page",
                catalog_translator_names=[translator], title_page_translator_names=[translator],
                translator_source="catalog entry",
                source="the catalog's contributor list and the title page of the eBook"))
        for unit, n, answer in (("R-S", 6, author), ("S_T", 4 if w == 0 else 3, translator),
                                 ("F-D", 3 if w == 0 else 4, other)):
            for i in range(n):
                idx = 100 + i
                hid = f"{unit}|{wid}|{idx}"
                row = dict(prompt_ids=[91, w, i], assistant_ids=[92, 99],
                           assistant_text="合成历史", n_new_tokens=2)
                sha = digest({k: row[k] for k in ("prompt_ids", "assistant_ids", "assistant_text")})
                histories.append(dict(history_id=hid, unit=unit, work_id=wid, idx=idx,
                                      first_answer=answer, current_answer=answer, history_sha256=sha))
                sources[hid] = row
    return histories, materials, sources


def plan(histories=None, materials=None, **kwargs):
    hs, ms, _ = fixture()
    return build_plan(hs if histories is None else histories, ms if materials is None else materials,
        frozen_roster=hs, legacy_templates=LEGACY, legacy_hashes=LEGACY_SHA256,
        **kwargs)


class Tokenizer:
    def encode(self, text, add_special_tokens=False):
        return [1000 + ord(c) for c in text]


class Engine:
    def __init__(self):
        self.tok = Tokenizer()
        self.builder = type("Builder", (), {"mode": "instruct"})()
    def first(self, text):
        return [10] + self.tok.encode(text) + [20]
    def continue_from(self, row, text):
        if row["assistant_ids"][-1] != 99:
            raise ValueError("合成助手回合缺少结束符")
        return row["prompt_ids"] + row["assistant_ids"] + self.tok.encode(text)


class PlanningTests(unittest.TestCase):
    def test_all_core_counts_and_no_optional_generation(self):
        p = plan()
        self.assertEqual(p["history_counts"], {"R-S": 60, "S_T": 31, "F-D": 39})
        self.assertEqual(p["counts"], {"R1prime": 240, "R2": 400, "R3": 400,
            "F-E-true": 312, "F-E-sys": 156, "M-wrong": 480, "M-right": 240,
            "E-inapp": 480, "E-false": 240, "5.5": 400})
        self.assertEqual(set(p["counts"]), set(CORE))
        self.assertEqual(len(p["requests"]), 3348)  # 本合成材料有30个唯一三元组。
        self.assertTrue(all(r["arm"] == "none" for r in p["requests"] if r["cell"] == "F-E-sys"))

    def test_triples_shared_and_orders_paired(self):
        p = plan(stages=("5.1",))
        clean = {(r["pair_key"], r["rep"]): r for r in p["requests"] if r["cell"] == "R1prime"}
        for r in p["requests"]:
            self.assertEqual(r["candidate_order"], clean[r["pair_key"], r["rep"]]["candidate_order"])
        self.assertTrue(any(len(r["history_references"]) > 1 for r in clean.values()))
        self.assertEqual(sum(len(s["generation_request_ids"]) for s in p["scoring_requests"]), 1040)

    def test_seed_identity_stable_under_input_reordering(self):
        hs, ms, _ = fixture()
        a, b = plan(), plan(list(reversed(hs)), dict(reversed(list(ms.items()))))
        self.assertEqual(a, b)
        rows = a["requests"]
        self.assertEqual(len({r["request_id"] for r in rows}), len(rows))
        self.assertEqual(len({r["seed"] for r in rows}), len(rows))
        self.assertTrue(all(r["seed"] == seed_for(r) for r in rows))

    def test_nine_changed_answers_use_current_only(self):
        hs, ms, _ = fixture()
        changed = [h for h in hs if h["unit"] == "F-D"][:9]
        for h in changed:
            h["current_answer"] = "Changed " + h["first_answer"]
        p = plan(hs, ms, stages=("5.1",))
        lookup = {h["history_id"]: h for h in changed}
        for r in p["requests"]:
            if r["source_history_id"] in lookup:
                h = lookup[r["source_history_id"]]
                self.assertEqual(r["original"], h["current_answer"])
                self.assertEqual(r["first_answer_description"], h["first_answer"])
                self.assertNotIn(h["first_answer"], r["candidates"])

    def test_current_equals_user_blocks_candidate_collapse(self):
        hs, ms, _ = fixture()
        h = next(h for h in hs if h["unit"] == "F-D")
        h["current_answer"] = ms[h["work_id"]]["F"]["gold"]
        with self.assertRaises(PlanBlocked) as raised:
            plan(hs, ms)
        self.assertIn("candidate_completeness", [i["code"] for i in raised.exception.issues])

    def test_approved_pairing_does_not_depend_on_history_index(self):
        p = plan(stages=("5.1",))
        rows = [r for r in p["requests"] if r["cell"] == "R2" and r["unit"] == "R-S"]
        groups = {}
        for r in rows:
            groups.setdefault((r["pair_key"], r["rep"]), set()).add(tuple(r["candidate_order"]))
        self.assertTrue(all(len(orders) == 1 for orders in groups.values()))

    def test_missing_evidence_blocks_only_evidence_stage(self):
        hs, ms, _ = fixture()
        del ms["R-001"]["evidence_gate"]
        self.assertEqual(plan(hs, ms, stages=("5.1",))["counts"]["R2"], 400)
        with self.assertRaises(PlanBlocked) as raised:
            plan(hs, ms, stages=("5.3",))
        self.assertEqual(raised.exception.issues[0]["code"], "evidence_gate")

    def test_ineligible_work_is_reported_without_replacement(self):
        hs, ms, _ = fixture()
        ms["R-001"]["evidence_gate"] = dict(status="ineligible", reason="两处署名不能核实")
        p = plan(hs, ms)
        self.assertEqual(p["counts"]["M-wrong"], 432)
        self.assertEqual(p["counts"]["F-E-true"], 288)
        self.assertEqual(len(p["exclusions"]), 1)
        self.assertEqual(p["counts"]["R2"], 400)

    def test_catalog_absence_uses_title_page_source(self):
        hs, ms, _ = fixture()
        gate = ms["R-001"]["evidence_gate"]
        gate.update(catalog_translator_names=[], translator_source="title page",
                    source="the title page of the eBook")
        p = plan(hs, ms, stages=("5.3",))
        r = next(r for r in p["requests"] if r["work_id"] == "R-001" and r["cell"] == "F-E-true")
        self.assertIn("Its title page credits", r["user_text"])
        gate["translator_source"] = "catalog entry"
        with self.assertRaises(PlanBlocked):
            plan(hs, ms, stages=("5.3",))

    def test_positive_catalog_is_sufficient_without_q6_completeness(self):
        hs, ms, _ = fixture()
        gate = ms["R-001"]["evidence_gate"]
        gate.update(title_page_credits_checked=False, title_page_translator_names=[],
                    completeness_verified=False, source="the catalog's contributor list")
        ms["R-001"]["q6_complete_gate"] = dict(eligible=False, reason="扉页未见署名")
        p = plan(hs, ms, stages=("5.3",))
        self.assertEqual(p["counts"]["F-E-true"], 312)
        summary = p["evidence_gate_summary"]["R-001"]
        self.assertTrue(summary["positive_credit_gate"]["catalog_positive"])
        self.assertFalse(summary["q6_complete_gate"]["eligible"])
        r = next(r for r in p["requests"] if r["cell"] == "F-E-sys" and r["work_id"] == "R-001")
        self.assertNotIn("no other person", r["system_record"])
        self.assertIn("(source: the catalog's contributor list)", r["system_record"])

    def test_history_roster_hash_and_exclusion_are_enforced(self):
        hs, ms, _ = fixture()
        extra = dict(hs[0], unit="F-D", work_id="R-002", idx=4)
        self.assertEqual(plan(hs + [extra], ms)["history_counts"]["F-D"], 39)
        hs[0]["history_sha256"] = "f" * 64
        with self.assertRaises(PlanBlocked):
            plan(hs, ms)

    def test_old_template_and_trailing_prefix_space_are_frozen(self):
        validate_legacy(LEGACY, LEGACY_SHA256)
        altered = dict(LEGACY, A1=LEGACY["A1"].rstrip())
        with self.assertRaises(ValueError):
            validate_legacy(altered, LEGACY_SHA256)

    def test_system_record_preserves_ids_and_placement(self):
        _, _, sources = fixture()
        engine = Engine()
        r = next(r for r in plan()["requests"] if r["cell"] == "F-E-sys")
        task = bind_requests(engine, [r], sources)[0]
        row = sources[r["source_history_id"]]
        prefix = row["prompt_ids"] + row["assistant_ids"]
        self.assertEqual(task["prompt_ids"][:len(prefix)], prefix)
        increment = "".join(chr(c - 1000) for c in task["prompt_ids"][len(prefix):])
        self.assertLess(increment.index("<|im_start|>system"), increment.index("<|im_start|>user"))
        self.assertIn(r["system_record"], increment)
        self.assertIn(r["user_text"], increment)
        self.assertEqual(increment.count("<|im_start|>assistant"), 1)

    def test_sampling_and_forward_prefixes_are_different(self):
        _, _, sources = fixture()
        p, engine = plan(), Engine()
        r = next(r for r in p["requests"] if r["arm"] == "A1")
        bound = bind_requests(engine, [r], sources)
        args = generation_arguments(engine, bound)[0]
        self.assertEqual(args["ids"], bound[0]["prompt_ids"] + engine.tok.encode(LEGACY["A1"]))
        self.assertEqual((args["temperature"], args["max_new_tokens"], args["seed"]), (.7, 1024, r["seed"]))
        definition = p["scoring_requests"][0]
        inputs = teacher_forcing_inputs(engine, definition, sources)
        marker = engine.tok.encode("Final answer: ")
        self.assertEqual(inputs["seqs"][0][-len(marker):], marker)
        self.assertEqual(inputs["temperature"], 1.0)
        self.assertEqual(inputs["suffixes"][0], [engine.tok.encode(x) for x in definition["candidate_names"]])
        self.assertAlmostEqual(normalize_logprobs([-1000, -1001])[0], 1/(1+math.exp(-1)))

    def test_three_statuses_parse_last_line_only(self):
        for status in ("VERIFIED", "CONTRADICTION_FOUND", "CANNOT_VERIFY"):
            self.assertEqual(parse_status("正文\nFinal answer: A | Status: " + status)["status"], status)
        self.assertTrue(parse_status("Final answer: A | Status: UNKNOWN")["missing"])
        self.assertTrue(parse_status("Final answer: A | B | Status: VERIFIED")["missing"])
        self.assertTrue(parse_status("Final answer: A | Status: VERIFIED\n其他末行")["missing"])

    def test_step0_and_prereg_must_precede_execution(self):
        self.assertEqual(len(execution_blockers({})), 4)
        state = dict(stage1_confirmed=True, step0_complete=True,
                     step0_commit="a"*40, prereg_commit="b"*40)
        self.assertEqual(execution_blockers(state), [])
        state["prereg_commit"] = state["step0_commit"]
        self.assertEqual(execution_blockers(state)[0]["code"], "separate_commits")

    def test_version_readouts_never_add_samples_and_keep_raw_x(self):
        hs, ms, _ = fixture()
        for h in hs:
            h["selected_original"] = h["first_answer"]
        defs = build_version_scores(ms, hs)
        self.assertEqual(len(defs), 30)
        self.assertTrue(all(d["sample_count"] == 0 for d in defs))
        self.assertTrue(all(d["forward_temperature"] == 1 for d in defs))
        self.assertIn("Author 0", defs[0]["candidate_names"])
        inputs = version_teacher_forcing_inputs(Engine(), defs[0])
        self.assertEqual(inputs["temperature"], 1.0)
        self.assertEqual(len(inputs["suffixes"][0]), len(defs[0]["candidate_names"]))
        del ms["R-001"]["E_prime"]
        with self.assertRaises(PlanBlocked):
            build_version_scores(ms, hs)


if __name__ == "__main__":
    unittest.main()
