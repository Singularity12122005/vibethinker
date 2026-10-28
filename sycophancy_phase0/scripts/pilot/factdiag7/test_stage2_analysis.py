"""离线统计的权重、配对、局部未知与原质量门槛测试。"""
import unittest
import json
import copy
from pathlib import Path
from tempfile import TemporaryDirectory

from stage2_analysis import (answer_events, apply_public_quality_gate, attach_review_status, collapse_histories, difference_stats, disjoint_difference,
                             existing_translator_knowledge,
                             map_response, observable_v_events, rate_stats, ratio_difference, ratio_stats, threshold)
from stage2_plan import identity


def row(work, history, value, *, event='W_side'):
    return dict(work_id=work, history_id=work + '|' + str(history), events={event: value})


class AnalysisTest(unittest.TestCase):
    def test_review_status_update_does_not_change_machine_values_or_pending_states(self):
        summary = dict(predictions={'one': {'machine_status': '未定'}},
                       cells={'X|S': {'rate': .25, 'status': '机器口径，待独立复核'},
                              'X|C': {'status': '待分类裁定，不删除受影响回答'}})
        review = dict(n_responses=40, n_views=100, quality_gate={'status': '待裁定'})
        attach_review_status(summary, review)
        self.assertEqual(summary['cells']['X|S']['rate'], .25)
        self.assertEqual(summary['cells']['X|C']['status'], '待分类裁定，不删除受影响回答')
        self.assertEqual(summary['predictions']['one']['machine_status'], '未定')
        self.assertIn('已完成', summary['validation']['independent_review'])

    def test_existing_translator_knowledge_is_read_without_changing_beliefs(self):
        beliefs = {'a': {'X': {'V_pre': '-'}}, 'b': {'X': {'V_pre': '0'}}}
        with TemporaryDirectory() as folder:
            source = Path(folder)
            missing = existing_translator_knowledge(source, beliefs)
            self.assertEqual(missing['missing_works'], ['a', 'b'])
            (source / 's0_public_summary.json').write_text(json.dumps({'literature_clean':
                [{'work_id': 'a', 'item_id': 'F-001-F', 'k': .625}]}), encoding='utf-8')
            value = existing_translator_knowledge(source, beliefs)
            self.assertEqual(value['by_work'], {'a': .625, 'b': None})
            self.assertEqual(beliefs['a']['X']['V_pre'], '-')

    def test_repeats_are_averaged_before_history_weight(self):
        rows = [row('a', 0, [0, 0])] * 4 + [row('a', 1, [1, 1])]
        collapsed = collapse_histories(rows, 'W_side')
        self.assertEqual(len(collapsed), 2)
        stats = rate_stats(rows, 'W_side')
        self.assertEqual(stats['lower']['history_equal'], .5)
        self.assertEqual(stats['n_generations'], 5)

    def test_work_equal_and_history_equal_remain_distinct(self):
        rows = [row('a', 0, [0, 0])] + [row('b', h, [1, 1]) for h in range(3)]
        stats = rate_stats(rows, 'W_side')
        self.assertEqual(stats['lower']['work_equal'], .5)
        self.assertEqual(stats['lower']['history_equal'], .75)

    def test_paired_difference_crosses_unknown_endpoints(self):
        a = [row('a', 0, [0, 1])] * 4 + [row('b', 0, [1, 1])] * 4
        b = [row('a', 0, [0, 0])] * 2 + [row('b', 0, [0, 1])] * 2
        stats = difference_stats(a, b, 'W_side')
        self.assertEqual(stats['lower'], 0)
        self.assertEqual(stats['upper'], 1)
        self.assertEqual(stats['n_histories'], 2)
        with self.assertRaisesRegex(ValueError, '历史集合不同'):
            difference_stats(a, b[:2], 'W_side')

    def test_missing_event_is_not_complete_case_deletion(self):
        rows = [row('a', 0, [1, 1]), row('a', 1, None)]
        stats = rate_stats(rows, 'W_side')
        self.assertIsNone(stats['lower'])
        self.assertEqual(stats['n_generations'], 2)
        self.assertEqual(stats['n_event_missing'], 1)

    def test_conditional_ratio_and_paired_change_do_not_smooth_zero_denominator(self):
        a = [row('a', 0, [0, 1])]
        a[0]['events']['M_side'] = [0, 1]
        ratio = ratio_stats(a)
        self.assertEqual(ratio['work_equal']['lower'], 0)
        self.assertIsNone(ratio['work_equal']['upper'])
        self.assertIsNone(ratio['conservative_interval'])
        self.assertIsNone(ratio_difference(a, a)['conservative_interval'])

    def test_disjoint_strata_use_different_works(self):
        result = disjoint_difference({'a': [.7, .8]}, {'b': [.1, .2]})
        self.assertAlmostEqual(result['lower'], .5)
        self.assertAlmostEqual(result['upper'], .7)
        with self.assertRaisesRegex(ValueError, '相同作品'):
            disjoint_difference({'a': [0, 0]}, {'a': [1, 1]})

    def test_thresholds_do_not_turn_overlap_into_failure(self):
        self.assertEqual(threshold({'conservative_interval': [.1, .4]}, minimum=.3), '未定')
        self.assertEqual(threshold({'conservative_interval': [.3, .4]}, minimum=.3), '通过')
        self.assertEqual(threshold({'conservative_interval': [-.3, .3]}, minimum=-.1, maximum=.1), '未定')
        self.assertEqual(threshold({'conservative_interval': None}, maximum=.05), '未定')

    def test_answer_review_missing_does_not_become_observed_failed(self):
        state = dict(status=None, review_missing=True, wrong=[0, 1], correct=[0, 1],
                     L_target=[0, 1], valid_generation=[0, 1], answer_coverage=[0, 1], reserved=[0, 1])
        events = answer_events(state)
        self.assertEqual(events['FAILED'], [0, 1])
        self.assertEqual(events['RESERVED'], [0, 1])

    def test_observable_v_states_preserve_unknown_and_do_not_redefine_groups(self):
        result = observable_v_events({'V_pre': '-', 'holder_correct': True}, [0, 1])
        self.assertEqual(result['V_correct_used'], [0, 1])
        self.assertEqual(result['V_correct_violated'], [0, 1])
        self.assertEqual(result['V_confident_wrong'], [0, 0])
        self.assertEqual(observable_v_events({'V_pre': '-', 'holder_correct': False}, None)['V_confident_wrong'], [1, 1])
        self.assertEqual(observable_v_events({'V_pre': '0', 'holder_correct': None}, None)['V_correct_used'], [0, 0])

    def test_local_unknown_preserves_whole_disjunction_and_unrelated_events(self):
        item = dict(item_id='one', work_id='one', structure='G1', title='A Tale', ebook='7',
                    target_relation='AUTHOR', sources={'author': 'fixture'},
                    people=[dict(type='X', name='Mira'), dict(type='GOLD', name='Arin')])
        r = dict(conflict_id='one', work_id='one', idx=0, path='X', candidate_type='X', arm='S', rep=0,
                 t=3, phase='fixture', truncated=False, looped=False)
        c = dict(relation=['AUTHOR', 'TRANSLATOR'], relation_detail=None, polarity='AFFIRM',
                 target='THIS_EDITION_OR_VERSION', scope_kind='EDITION', scope_key='ebook:7',
                 basis='CREDITED', hedged=False, flags=[], event_eligible=True, quote='A synthetic sentence.')
        ex = {identity(r) + '|X': {'extraction': {'parse_status': 'OK', 'claims': [c]}},
              identity(r) + '|GOLD': {'extraction': {'parse_status': 'OK', 'claims': []}}}
        outcome = {'result': {'answer': dict(status='ANSWERED_CORRECT', correct=[1, 1], wrong=[0, 0],
                    answer_unjudgeable=False, L_target=[0, 0], valid_generation=[1, 1], answer_coverage=[1, 1])}}
        result = map_response(r, item, ex, outcome, include_translator=False)
        self.assertEqual(len(result['classification_unknown']), 1)
        self.assertEqual(result['events']['W_side'], [0, 1])
        self.assertIsInstance(result['events']['W_false'], list)
        self.assertEqual(result['events']['E_wrong'], [0, 0])
        self.assertEqual(result['mapped']['X']['claims'][0]['relation'], ['AUTHOR', 'TRANSLATOR'])

    def test_failed_quality_gate_withholds_only_w_dependent_results(self):
        metric = {'lower': .4, 'upper': .6, 'n_generations': 40, 'n_unknown': 3}
        summary = dict(status='fixture', cells={'X|S': {
            'metrics': {k: dict(metric) for k in ('W_false', 'E_wrong', 'M_side', 'V_ext', 'false_deny',
                                                'E1_W1', 'V_correct_used', 'all_claims_judgeable')},
            'W_side_given_M_side': dict(metric)}},
            paired_changes={'one': {k: dict(metric) for k in ('W_side', 'M_side', 'E_wrong')}},
            V_strata={'X': {'groups': {'-': {'rates': {'S': {'W_side': dict(metric), 'E_wrong': dict(metric)}},
                                                 'delta_press': {'W_side': dict(metric)}}}}},
            V_comparisons={'X': {'holder_correct_works': ['a'], 'Q6_trigger_rate': dict(metric)}},
            predictions={k: {'machine_status': '通过', 'conservative_interval': [.3, .4]}
                         for k in ('Q2_E_X', 'Q2_M_side_X_A1', 'Q6_conditional_trigger')})
        private = copy.deepcopy(summary)
        apply_public_quality_gate(summary, {'quality_gate': {'full_denominator_available': True, 'status': '未通过'}})
        metrics = summary['cells']['X|S']['metrics']
        for key in ('W_false', 'E1_W1', 'V_correct_used'):
            self.assertNotIn('lower', metrics[key])
            self.assertEqual(metrics[key]['n_generations'], 40)
            self.assertEqual(metrics[key]['n_unknown'], 3)
        for key in ('E_wrong', 'M_side', 'V_ext', 'false_deny', 'all_claims_judgeable'):
            self.assertEqual(metrics[key]['lower'], .4)
        self.assertEqual(summary['paired_changes']['one']['M_side']['lower'], .4)
        self.assertEqual(summary['predictions']['Q2_M_side_X_A1']['machine_status'], '通过')
        self.assertIsNone(summary['predictions']['Q6_conditional_trigger']['conservative_interval'])
        self.assertEqual(private['cells']['X|S']['metrics']['W_false']['lower'], .4)


if __name__ == '__main__':
    unittest.main()
