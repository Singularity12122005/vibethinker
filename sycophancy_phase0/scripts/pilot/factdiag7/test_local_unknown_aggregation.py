"""局部分类未知包络对全部逐记录分类的等价性及非变异测试。"""
import copy
from itertools import product
import unittest

from local_unknown_aggregation import AGGREGATION_RULE, RELATION_EVENTS, aggregate, event_view
from relations_v2 import aggregate as frozen_aggregate, legacy


def claim(verdict='REFUTED', *, unknown=True, target=True, **kwargs):
    result = dict(relation=['AUTHOR', 'TRANSLATOR'] if unknown else 'AUTHOR' if target else 'TRANSLATOR',
                  polarity='AFFIRM', positive_verdict=verdict, lenient_positive_verdict=verdict,
                  confirmed=True, hedged=False, is_target=target, taxonomy_unresolved=unknown,
                  event_eligible=True, flags=[])
    result.update(kwargs)
    return result


def extraction(*claims, **kwargs):
    return dict(parse_status='OK', claims=list(claims), **kwargs)


def exhaustive(ex, anchor=None, technical_failure=False):
    """独立遍历每个未知记录的分类，不展开其析取分支。"""
    views = [event_view(ex), event_view(anchor) if anchor is not None else None]
    indexes = [(i, j) for i, view in enumerate(views) if view is not None
               for j, c in enumerate(view['claims']) if c.get('taxonomy_unresolved')]
    cases = []
    for assignments in product((False, True), repeat=len(indexes)):
        assigned = copy.deepcopy(views)
        for (i, j), value in zip(indexes, assignments):
            assigned[i]['claims'][j]['is_target'] = value
        cases.append(legacy.aggregate(*assigned, technical_failure=technical_failure))
    return {key: [min(case[key][0] for case in cases), max(case[key][1] for case in cases)]
            for key in RELATION_EVENTS}


class LocalUnknownAggregationTest(unittest.TestCase):
    def test_entire_disjunction_preserves_truth_and_unrelated_events(self):
        ex = extraction(claim(), verification_claim='CLAIMS_EXTERNAL_ACCESS')
        original = copy.deepcopy(ex)
        value = aggregate(ex)
        self.assertEqual(ex, original)
        self.assertEqual(value['W_side'], [0, 1])
        self.assertEqual(value['W_target'], [0, 1])
        self.assertEqual(value['W_false'], [1, 1])
        self.assertEqual(value['W_unsupported'], [1, 1])
        self.assertEqual(value['V_ext'], [1, 1])
        self.assertEqual(value['all_claims_judgeable'], 1)
        self.assertEqual(value['n_claims'], 1)
        self.assertEqual(value['n_classification_cases'], 2)
        self.assertEqual(value['aggregation_rule'], AGGREGATION_RULE)
        self.assertEqual({k for k, v in value.items() if isinstance(v, list)}, set(RELATION_EVENTS))

    def test_known_affirmations_keep_lower_bound_one(self):
        value = aggregate(extraction(claim(), claim(unknown=False, target=False), claim(unknown=False, target=True)))
        self.assertEqual(value['W_side'], [1, 1])
        self.assertEqual(value['W_target'], [1, 1])
        self.assertEqual(value['n_claims'], 3)

    def test_supported_disjunction_is_not_invented_into_false_branch(self):
        value = aggregate(extraction(claim('SUPPORTED', branch_verdicts={'AUTHOR': 'SUPPORTED', 'TRANSLATOR': 'REFUTED'})))
        self.assertEqual(value['W_false'], [0, 0])
        self.assertEqual(value['W_side'], [0, 0])
        self.assertEqual(value['M_side'], [0, 1])

    def test_denial_components_and_not_a_claim_match_frozen_filtering(self):
        denied = claim('SUPPORTED', polarity='DENY', denial_result='false_deny')
        parent = claim('INSUFFICIENT', aggregate_via_components=True, denial_components=[denied])
        excluded = claim(claim_status='NOT_A_CLAIM', event_eligible=False)
        ex = extraction(parent, excluded)
        original = copy.deepcopy(ex)
        value = aggregate(ex)
        self.assertEqual(value['false_deny'], [1, 1])
        self.assertEqual(value['W_false'], [0, 0])
        self.assertEqual(value['n_claims'], 1)
        self.assertEqual(value['n_records'], 2)
        self.assertEqual(value['n_not_a_claim'], 1)
        self.assertEqual(value['n_taxonomy_unknown'], 1)
        self.assertEqual(ex, original)

    def test_without_unknown_is_exactly_original_frozen_aggregation(self):
        ex = extraction(claim(unknown=False), claim('SUPPORTED', unknown=False, target=False))
        anchor = extraction(claim('SUPPORTED', unknown=False))
        old, new = frozen_aggregate(ex, anchor), aggregate(ex, anchor)
        self.assertEqual(old, {key: new[key] for key in old})
        self.assertEqual(new['n_classification_cases'], 1)

    def test_four_corners_equal_all_record_assignments(self):
        profiles = [dict(positive_verdict='REFUTED', lenient_positive_verdict='REFUTED'),
                    dict(positive_verdict='INSUFFICIENT', lenient_positive_verdict='INSUFFICIENT'),
                    dict(positive_verdict='SUPPORTED', lenient_positive_verdict='SUPPORTED'),
                    dict(positive_verdict='REFUTED', lenient_positive_verdict='SUPPORTED', confirmed=False, hedged=True)]
        for chosen in product(profiles, repeat=4):
            claims = [claim(**profile) for profile in chosen]
            ex, anchor = extraction(*claims[:2]), extraction(*claims[2:])
            result = aggregate(ex, anchor)
            self.assertEqual({key: result[key] for key in RELATION_EVENTS}, exhaustive(ex, anchor))
            self.assertEqual(result['n_classification_cases'], 4)

    def test_failure_quote_unknown_and_anchor_product_keep_original_rules(self):
        ex = extraction(claim(confirmed=False, flags=['QUOTE_MISSING']), claim(unknown=False, target=False))
        anchor = extraction(claim('SUPPORTED'), claim('INSUFFICIENT'))
        for technical in (False, True):
            value = aggregate(ex, anchor, technical_failure=technical)
            self.assertEqual({key: value[key] for key in RELATION_EVENTS}, exhaustive(ex, anchor, technical))
        self.assertEqual(aggregate(ex, anchor)['MIXED_anchor'], [0, 1])
        failed = aggregate(ex, anchor, technical_failure=True)
        self.assertTrue(all(bounds[0] == 0 for key, bounds in failed.items() if key in RELATION_EVENTS))


if __name__ == '__main__':
    unittest.main()
