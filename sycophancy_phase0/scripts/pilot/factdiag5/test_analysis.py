"""按作品留一、缺测及收益符号的合成处理器测试。"""
import copy
import unittest

from .analysis import additive_leave_one, g4_leave_one, net_benefit, specificity, version_features


def rows():
    return [dict(history_id=f"{w}|{i}", work_id=w, b=(-1 if i == 0 else 1), z0=.2 + .6 * i,
                 specificity_difference=float(i), recognizable=True, sample_modes_stable=None,
                 a=.2 + i * .1, f=.4 + i * .1, m_N=-.5 + i, m_S=.7 + i,
                 unit="R-S" if i == 0 else "F-D") for w in ("A", "B", "C") for i in range(2)]


class AnalysisTests(unittest.TestCase):
    def test_specific_branch_survives_missing_sample_modes(self):
        r = dict(recognizable=True, specificity_difference=2., sample_modes_stable=None)
        self.assertEqual(specificity(r, 1.), "特异")
        self.assertEqual(specificity(r, 2.), "未定")
        self.assertEqual(specificity(dict(r, sample_modes_stable=True), 2.), "泛化")
        self.assertEqual(specificity(dict(r, recognizable=False), 1.), "未定")

    def test_g4_holdout_labels_never_set_its_own_threshold(self):
        original = rows()
        altered = copy.deepcopy(original)
        for r in altered:
            if r["work_id"] == "A":
                r.update(b=100., specificity_difference=999., z0=.999)
        a, b = g4_leave_one(original), g4_leave_one(altered)
        self.assertEqual(a["folds"]["A"], b["folds"]["A"])
        self.assertNotIn("A", a["folds"]["A"]["training_works"])
        self.assertEqual(len(a["predictions"]), len(original))

    def test_additive_holdout_and_constant_offset(self):
        original = rows()
        altered = copy.deepcopy(original)
        for r in altered:
            if r["work_id"] == "A":
                r["m_S"] = 999.
        a, b = additive_leave_one(original), additive_leave_one(altered)
        for model in ("M0", "M1", "M2"):
            self.assertEqual(a[model]["folds"]["A"], b[model]["folds"]["A"])
        for row in a["M0"]["predictions"]:
            self.assertAlmostEqual(row["predicted_delta"], 1.2)

    def test_benefit_sign_and_decomposition(self):
        r = [dict(work_id="A", b=.8), dict(work_id="B", b=-.2)]
        self.assertAlmostEqual(net_benefit(r, [True, True])["net"], .3)
        self.assertAlmostEqual(net_benefit(r, [True, False])["rescued_damage"], .4)
        self.assertAlmostEqual(net_benefit(r, [False, True])["lost_protection"], .1)
        with self.assertRaises(ValueError):
            net_benefit([dict(work_id="A", b=None)], [True])

    def test_version_features_use_raw_x_and_preserve_missing_modes(self):
        versions = [dict(definition=dict(work_id="A", kind=kind, candidate_names=["X", "T"]),
                        full_name_logp=[value, -2.]) for kind, value in (
                            ("scope_original", -20.), ("scope_other", -40.), ("wording", -25.))]
        h = [dict(history_id="A|1", work_id="A", selected_original="X")]
        material = [dict(work_id="A", version_control_applicable=False)]
        r = version_features(versions, h, material, candidate_support={"A": .25}, clean_yes_support={})[0]
        self.assertEqual((r["z_scope"], r["z_wording"], r["specificity_difference"]), (20., 5., 15.))
        self.assertTrue(r["recognizable"])
        self.assertIsNone(r["sample_modes_stable"])
        self.assertFalse(r["version_control_applicable"])


if __name__ == "__main__":
    unittest.main()
