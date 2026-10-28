"""完整命题比较与未知分母的自造短例测试。"""
import unittest

from stage2_review_report import align_views, binary_agreement, event_comparison, extraction_comparison, quality_gate


def claim(relation='TRANSLATOR', **kwargs):
    value = dict(polarity='AFFIRM', relation=relation, relation_detail=None, target='THIS_EDITION_OR_VERSION',
                 basis='CREDITED', scope_key='ebook:1', scope_kind='EDITION', scope_text=None,
                 hedged=False, broad_denial=False, exclusivity=None, event_eligible=True)
    value.update(kwargs)
    return value


class ReviewReportTest(unittest.TestCase):
    def test_blinded_view_order_is_preserved_and_aligned_by_candidate(self):
        people = {'X': {'name': 'Mira'}, 'GOLD': {'name': 'Arin'}, 'T': {'name': 'Nora'}}
        entries = [{'candidate': name} for name in ['Nora', 'Arin', 'Mira']]
        result = align_views(people, ['X', 'GOLD', 'T'], entries, entries)
        self.assertEqual([kind for kind, entry in result], ['T', 'GOLD', 'X'])
        with self.assertRaises(ValueError):
            align_views(people, ['X', 'GOLD', 'T'], entries, list(reversed(entries)))

    def test_missing_claim_counts_against_full_comparison(self):
        a = {'claims': [claim(), claim('EDITOR')]}
        b = {'claims': [claim()]}
        value = extraction_comparison(a, b)
        self.assertFalse(value['claim_key_set'])
        self.assertFalse(value['all_claim_fields']['polarity'])
        self.assertFalse(value['complete_claim_fields'])
        self.assertEqual(len(value['machine_only_keys']), 1)

    def test_relation_order_is_irrelevant_but_other_predicate_is_not(self):
        a = {'claims': [claim(['EDITOR', 'TRANSLATOR'])]}
        b = {'claims': [claim(['TRANSLATOR', 'EDITOR'])]}
        self.assertTrue(extraction_comparison(a, b)['claim_key_set'])
        a = {'claims': [claim('OTHER', relation_detail='OWNS_ARCHIVE')]}
        b = {'claims': [claim('OTHER', relation_detail='FUNDS_ARCHIVE')]}
        self.assertFalse(extraction_comparison(a, b)['claim_key_set'])

    def test_same_field_multisets_do_not_hide_different_field_pairing(self):
        a = {'claims': [claim('TRANSLATOR', hedged=False), claim('EDITOR', hedged=True)]}
        b = {'claims': [claim('TRANSLATOR', hedged=True), claim('EDITOR', hedged=False)]}
        value = extraction_comparison(a, b)
        self.assertTrue(value['all_claim_fields']['hedged'])
        self.assertFalse(value['complete_claim_fields'])

    def test_not_a_claim_is_retained_but_excluded_from_claim_keys(self):
        a = {'claims': [claim(), claim('EDITOR', claim_status='NOT_A_CLAIM', event_eligible=False)]}
        b = {'claims': [claim()]}
        self.assertTrue(extraction_comparison(a, b)['claim_key_set'])

    def test_local_unknown_keeps_full_denominator_and_determined_subset_is_separate(self):
        result = event_comparison([([1, 1], [1, 1]), ([0, 1], [0, 0]), ([0, 1], [0, 1]), ([0, 0], [1, 1])])
        self.assertEqual(result['n_planned'], 4)
        self.assertEqual(result['strict_confirmed_event']['n'], 4)
        self.assertAlmostEqual(result['strict_confirmed_event']['raw_agreement'], .75)
        self.assertEqual(result['both_determined_event']['n'], 2)
        self.assertEqual(result['both_determined_event']['raw_agreement'], .5)
        with self.assertRaisesRegex(ValueError, '不能删去分母'):
            event_comparison([(None, [0, 0])])

    def test_kappa_and_constant_marginal(self):
        result = binary_agreement([(0, 0), (1, 1), (0, 1), (1, 0)])
        self.assertEqual(result['raw_agreement'], .5)
        self.assertEqual(result['kappa'], 0)
        self.assertIsNone(binary_agreement([(0, 0), (0, 0)])['kappa'])

    def test_quality_gate_uses_all_40_and_original_threshold(self):
        pairs = [([0, 0], [0, 0])] * 30 + [([0, 1], [1, 1])] * 10
        gate = quality_gate(event_comparison(pairs))
        self.assertEqual(gate['raw_agreement'], .75)
        self.assertTrue(gate['full_denominator_available'])
        self.assertEqual(gate['status'], '未通过')
        passing = [([0, 0], [0, 0])] * 32 + [([0, 1], [1, 1])] * 8
        self.assertEqual(quality_gate(event_comparison(passing))['status'], '通过')
        self.assertFalse(quality_gate(event_comparison(pairs[:30]))['full_denominator_available'])


if __name__ == '__main__':
    unittest.main()
