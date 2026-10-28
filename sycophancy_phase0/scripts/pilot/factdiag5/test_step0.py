"""5.0的核心计数、损失方向与报告表格验证；只使用合成记录。"""
from pathlib import Path
from types import SimpleNamespace
import importlib.util
import unittest

_spec = importlib.util.spec_from_file_location("factdiag5_step0_under_test", Path(__file__).with_name("step0.py"))
step0 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(step0)


class StepZeroTests(unittest.TestCase):
    def test_missing_event_is_not_replaced_with_zero(self):
        r = step0.rate([1, None, 0])
        self.assertEqual(r["point"], .5)
        self.assertEqual(r["bounds"], [1/3, 2/3])
        self.assertEqual((r["missing"], r["planned"]), (1, 3))
        self.assertIsNone(step0.rate([])["point"])

    def test_b_positive_means_a1_is_costly(self):
        cost = step0.difference(step0.rate([1, 1, 1, 0]), step0.rate([1, 0, 0, 0]))
        self.assertEqual(cost["point"], .5)
        self.assertEqual(cost["bounds"], [.5, .5])

    def test_split_half_covariance_is_unbiased_sample_covariance(self):
        self.assertEqual(step0.covariance([0, 1, 2], [2, 1, 0]), -1)
        self.assertIsNone(step0.covariance([1], [2]))

    def test_modes_keep_ties_without_inventing_a_winner(self):
        result = step0.mode_table(["A", "B", "A", "B"])
        self.assertEqual(result["modes"], ["A", "B"])
        self.assertEqual(result["modal_share"], .5)

    def test_combined_works_do_not_merge_equal_history_indices(self):
        rows = [dict(work_id="A", idx=0, value=1)] + [dict(work_id="B", idx=0, value=0)]*3
        result = step0.grouped_rate(rows, lambda r: r["value"])
        self.assertEqual(result["histories"], 2)
        self.assertEqual(result["point"], .25)
        self.assertEqual(result["history_equal"], .5)

    def test_joint_count_and_two_denial_denominators_are_distinct(self):
        def row(stance, c1, c2):
            return dict(unit="R-S", condition="base", bad=False, judge=dict(stance=stance),
                        propositions=dict(C1=dict(label=c1), C2=dict(label=c2)))
        rows = [row("USER", "AFFIRM", "DENY"), row("ORIG", "AFFIRM", "DENY"),
                row("USER", "UNJUDGEABLE", "UNMENTIONED")]
        common = SimpleNamespace(known_stance=lambda r: True,
            p3=SimpleNamespace(old=SimpleNamespace(basic_bad=lambda r: r["bad"])))
        result = step0.cross_table(rows, common)
        self.assertEqual(result["wrong_target_and_author_affirm"], 1)
        self.assertEqual((result["C2_deny_all_answers"], result["C2_deny_ORIG_only"]), (2, 1))
        self.assertEqual(result["table"]["USER"]["UNDETERMINED"], 1)

    def test_noncorrect_final_answer_has_unit_target_loss(self):
        old = SimpleNamespace(basic_bad=lambda r: r.get("bad", False),
                              parse_final=lambda text, material: dict(value=text or None))
        material = {"R": {"gold": "A"}, "F": {"gold": "T"}}
        self.assertEqual(step0.target_loss(dict(unit="F-D", assistant_text="T"), material, old), 0)
        self.assertEqual(step0.target_loss(dict(unit="F-D", assistant_text=""), material, old), 1)
        self.assertEqual(step0.target_loss(dict(unit="F-D", assistant_text="T", bad=True), material, old), 1)

    def test_render_escapes_history_columns_and_has_stable_execution_language(self):
        summary = dict(source_histories_verified=193, answer_changes=[dict(history_id="F-D|R-001|13", first_answer="A", current_answer="B")],
            step5_0a=[], step5_0b=[], step5_0c=dict(works=[], limitation="不覆盖匿名候选"), step5_0d=[],
            step5_0e=dict(table={"USER": dict(AFFIRM=193, UNDETERMINED=7, DENY=0),
                                      "ORIG": dict(AFFIRM=252, UNDETERMINED=28, DENY=0)},
                wrong_target_and_author_affirm=193, C2_deny_all_answers=25, C2_deny_ORIG_only=24,
                undetermined_definition="旧标签不可判"),
            definitions=dict(b="b=有A1损失减无A1损失", split_half="零基重复号分半"), interpretation="描述限制")
        text = step0.render(summary)
        self.assertIn("|F-D / R-001 / 13|A|B|", text)
        self.assertNotIn("|F-D|R-001|13|", text)
        self.assertNotIn("尚未提交", text)
        self.assertNotIn("本次未提交", text)
        self.assertIn("193条同时明确肯定", text)
        self.assertIn("旧口径交叉计数", text)


if __name__ == "__main__":
    unittest.main()
