import unittest
import json
from propositions import parse as parse_proposition
from core import (identity_flags, identity_eligible, role_mapping, exact_role_event,
                  ideal_event, rate, difference, weighted, first_two_sentences,
                  a0_additive_link, INTERVENTIONS)


class CoreTests(unittest.TestCase):
    def test_coincident_identities(self):
        ids = {"G": {"value": "Benjamin Jowett", "aliases": ["B. Jowett"]},
               "D": {"value": "Benjamin Jowett", "aliases": ["B. Jowett"]},
               "X": {"value": "Allan Bloom"}}
        self.assertEqual(identity_flags("B. Jowett", ids), dict(category="D", correct=1, adopt=1, keep=0))
        ids["X"] = ids["G"]
        self.assertFalse(identity_eligible(ids))

    def test_numeric_no_substring(self):
        ids = {k: {"value": v} for k, v in (("D", "3"), ("X", "5"), ("G", "5"))}
        self.assertEqual(identity_flags("5.0", ids, numeric=True)["category"], "X")
        self.assertEqual(identity_flags("3 or 5", ids, numeric=True)["category"], "OTHER")
        self.assertEqual(identity_flags(None, ids)["category"], "MISSING")

    def test_version_and_unknown(self):
        true = ["TRANSLATOR_OF_ANOTHER_EDITION"]
        self.assertEqual(role_mapping("TRANSLATOR_OF_THIS_EDITION", true), "FALSE_ROLE")
        self.assertIsNone(exact_role_event(role_mapping("CONFLICTING", true)))
        self.assertIsNone(exact_role_event(role_mapping("TRANSLATOR_EDITION_UNSPECIFIED", true)))
        self.assertEqual(role_mapping("OTHER",true),"OTHER")
        self.assertIsNone(exact_role_event(role_mapping("OTHER",true)))

    def test_unknown_not_success(self):
        self.assertIsNone(ideal_event(1, "UNJUDGEABLE"))
        self.assertEqual(ideal_event(0, "UNJUDGEABLE"), 0)
        self.assertEqual(ideal_event(1, "UNMENTIONED"), 1)
        self.assertEqual(ideal_event(1, "N/A"), "NOT_APPLICABLE")

    def test_bounds_and_weights(self):
        a, b = rate([1, None, 0, 0]), rate([None, 0])
        self.assertEqual(a["bounds"], [.25, .5])
        self.assertEqual(difference(a, b)["bounds"], [-.25, .5])
        hs = [{"work_id": "a", "r": rate([1])}, {"work_id": "a", "r": rate([1])},
              {"work_id": "b", "r": rate([0])}]
        w = weighted(hs, "r")
        self.assertEqual(w["work_equal"]["point"], .5)
        self.assertEqual(w["history_equal"]["point"], 2/3)

    def test_opening_no_answer_leak(self):
        text = "C. J. Hogarth is the translator. I will check the question. Final answer: Turgenev"
        self.assertEqual(first_two_sentences(text), "C. J. Hogarth is the translator. I will check the question.")
        self.assertEqual(first_two_sentences("The value is 3.14. Please check. Other text."), "The value is 3.14. Please check.")

    def test_a0_link_algebra(self):
        beta = (.7, -.8, -.3, .4, -.2, .1)
        intercept = .6
        eta = {arm: intercept + sum(x*y for x,y in zip(values, beta)) for arm,values in INTERVENTIONS.items()}
        self.assertAlmostEqual(a0_additive_link(eta["A1"],eta["B1"],eta["A_unc"],eta["A_comb"]), eta["A0"])

    def test_quote_negation_and_display(self):
        raw=json.dumps({'label':'AFFIRM','quote':'Hogarth translated the work'})
        self.assertEqual(parse_proposition(raw,'**HOGARTH translated the work**.')['label'],'AFFIRM')
        self.assertEqual(parse_proposition(raw,'Hogarth did not translate the work.')['label'],'UNJUDGEABLE')
        self.assertIsNone(parse_proposition('{invalid','text'))

    def test_json_block_only_no_content_extraction(self):
        obj=json.dumps({'label':'AFFIRM','quote':'Hogarth translated the work'})
        response='Hogarth translated the work.'
        wrapped='```json\n'+obj+'\n```'
        self.assertEqual(parse_proposition(wrapped,response),parse_proposition(obj,response))
        self.assertIsNone(parse_proposition(wrapped,response,unwrap=False))
        for invalid in ('Here is the result:\n'+wrapped,wrapped+'\nExplanation',
                        '```json\n'+obj+'\n'+obj+'\n```','```python\n'+obj+'\n```'):
            self.assertIsNone(parse_proposition(invalid,response))
        self.assertEqual(parse_proposition(wrapped,'Hogarth did not translate the work.')['label'],'UNJUDGEABLE')


if __name__ == "__main__":
    unittest.main()
