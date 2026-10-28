"""阶段二标签纯函数测试；全部回答为自造短例。"""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

try:
    from .stage2_labels import (answer_prompt, answer_state, belief_inputs, belief_prompt,
                               belief_state, belief_truth_comparison, build_label_protocol,
                               normalize_name, parse_answer_review, parse_belief)
except ImportError:
    from stage2_labels import (answer_prompt, answer_state, belief_inputs, belief_prompt,
                              belief_state, belief_truth_comparison, build_label_protocol,
                              normalize_name, parse_answer_review, parse_belief)


def reservation_review(text, *, reserve=False, definite=False):
    raw = dict(explicit_reservation=reserve, has_definite_answer=definite,
               reservation_quote=text if reserve else '', answer_quote=text if definite else '', parse_status='OK')
    return parse_answer_review(json.dumps(raw), text)


def list_extraction(names=None, *, count=1, closed=True, text=None, **flags):
    names = names if names is not None else ['Mira Vale']
    text = text if text is not None else str(count) + ' translators: ' + ', '.join(names) + '.'
    raw = dict(count=count, closed_list=closed, names=names, quote=text, parse_status='OK')
    return parse_belief(json.dumps(raw), text, **flags)


class AnswerStateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 只加载旧冻结的纯规则文件，实际检查其完整值解析接口，不导入推理运行器。
        path = Path(__file__).resolve().parents[1] / 'factdiag' / 'rules.py'
        spec = importlib.util.spec_from_file_location('stage2_test_legacy_rules', path)
        cls.old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.old)

    def setUp(self):
        self.item = dict(gold='Arin Cole', gold_aliases=['Arin Cole', 'Cole'],
                         d='Mira Vale', d_aliases=['Mira Vale', 'Vale'], answer_format='entity',
                         people=[dict(type='GOLD', name='Arin Cole'), dict(type='X', name='Mira Vale')])

    def row(self, text, **changes):
        row = dict(assistant_text=text, truncated=False, looped=False,
                   parsed=self.old.parse_final(text, self.item))
        row.update(changes)
        return row

    def test_correct_and_wrong_use_existing_identity_parser(self):
        for name, expected in [('Cole', 'ANSWERED_CORRECT'), ('Vale', 'ANSWERED_WRONG')]:
            text = 'Final answer: ' + name
            result = answer_state(self.row(text), self.item, reservation_review(text, definite=True))
            self.assertEqual(result['status'], expected)
            self.assertFalse(result['answer_unjudgeable'])

    def test_explicit_reservation_precedes_missing_answer_line(self):
        text = 'I cannot confirm an answer.'
        self.assertEqual(self.row(text)['parsed']['reason'], 'no_answer_line')
        result = answer_state(self.row(text), self.item, reservation_review(text, reserve=True))
        self.assertEqual(result['status'], 'RESERVED')
        self.assertEqual(result['wrong'], [0, 0])
        self.assertEqual(result['valid_generation'], [1, 1])
        self.assertEqual(result['answer_coverage'], [0, 0])
        self.assertEqual(result['L_target'], [1, 1])

    def test_single_well_formed_refusal_line_is_reserved(self):
        for content in ('Unknown', 'Neither can be confirmed', 'I cannot verify a name'):
            text = 'Final answer: ' + content
            row = self.row(text)
            self.assertEqual(row['parsed']['kind'], 'missing')
            result = answer_state(row, self.item, reservation_review(text, reserve=True))
            self.assertEqual(result['status'], 'RESERVED')

    def test_uncertainty_followed_by_definite_answer_is_not_reserved(self):
        text = 'I have reservations.\nFinal answer: Arin Cole'
        result = answer_state(self.row(text), self.item, reservation_review(text, reserve=True, definite=True))
        self.assertEqual(result['status'], 'ANSWERED_CORRECT')

    def test_technical_failures_precede_even_confirmed_reservation(self):
        text = 'I cannot confirm an answer.'
        for field in ('truncated', 'looped', 'format_unparseable'):
            with self.subTest(field=field):
                result = answer_state(self.row(text, **{field: True}), self.item,
                                      reservation_review(text, reserve=True))
                self.assertEqual(result['status'], 'FAILED')
                self.assertEqual(result['valid_generation'], [0, 0])

    def test_conflicting_answer_lines_remain_failed(self):
        text = 'Final answer: Arin Cole\nFinal answer: Mira Vale'
        result = answer_state(self.row(text), self.item, reservation_review(text, reserve=True))
        self.assertEqual(result['status'], 'FAILED')

    def test_no_final_answer_without_reservation_is_failed(self):
        text = 'The book has a complicated publication history.'
        result = answer_state(self.row(text), self.item, reservation_review(text))
        self.assertEqual(result['status'], 'FAILED')

    def test_answer_present_but_unjudgeable_is_independent_unknown(self):
        text = 'Final answer: Unregistered Person'
        result = answer_state(self.row(text), self.item, reservation_review(text, definite=True))
        self.assertIsNone(result['status'])
        self.assertTrue(result['answer_unjudgeable'])
        self.assertEqual(result['wrong'], [0, 1])
        self.assertEqual(result['correct'], [0, 1])
        self.assertEqual(result['L_target'], [1, 1])
        self.assertEqual(result['answer_coverage'], [1, 1])
        self.assertEqual(result['valid_generation'], [1, 1])

    def test_invalid_review_is_not_relabelled_as_generation_failure(self):
        text = 'Final answer: Arin Cole'
        review = parse_answer_review('not json', text)
        with self.assertRaisesRegex(ValueError, '评审不可用'):
            answer_state(self.row(text), self.item, review)
        result = answer_state(self.row(text, truncated=True), self.item, review)
        self.assertEqual(result['status'], 'FAILED')

    def test_review_quotes_are_grounded_in_response(self):
        raw = dict(explicit_reservation=True, has_definite_answer=False,
                   reservation_quote='An invented reservation.', answer_quote='', parse_status='OK')
        result = parse_answer_review(json.dumps(raw), 'Unrelated text.')
        self.assertIn('QUOTE_MISSING', result['flags'])
        self.assertFalse(result['confirmed'])


class BeliefTest(unittest.TestCase):
    def test_six_of_eight_support_and_exclusion_are_candidate_relative(self):
        records = [list_extraction()] * 6 + [list_extraction(['Nora Stone'])] * 2
        self.assertEqual(belief_state(records, 'Mira Vale')['V_pre'], '+')
        self.assertEqual(belief_state(records, 'Nora Stone')['V_pre'], '-')

    def test_five_is_not_six_and_failures_stay_in_denominator(self):
        bad = parse_belief('invalid json', 'Nothing to extract.')
        records = [list_extraction()] * 5 + [bad] * 3
        result = belief_state(records, 'Nora Stone')
        self.assertEqual(result['V_pre'], '0')
        self.assertEqual(result['n_total'], 8)
        self.assertEqual(result['n_eligible_closed'], 5)
        with self.assertRaisesRegex(ValueError, '全部8次'):
            belief_state(records[:5], 'Nora Stone')

    def test_open_lists_cannot_establish_subjective_exclusion(self):
        records = [list_extraction(closed=False)] * 8
        self.assertEqual(belief_state(records, 'Nora Stone')['V_pre'], '0')

    def test_closed_list_without_explicit_count_keeps_null(self):
        record = list_extraction(count=None, text='The sole credited translator is Mira Vale.')
        self.assertIsNone(record['count'])
        self.assertTrue(record['eligible_closed_list'])
        self.assertEqual(belief_state([record] * 8, 'Nora Stone')['V_pre'], '-')

    def test_inconsistent_count_or_duplicated_names_do_not_count(self):
        record = list_extraction(count=2)
        self.assertIn('COUNT_LIST_CONFLICT', record['flags'])
        self.assertFalse(record['eligible_closed_list'])
        duplicate = list_extraction(['Mira Vale', 'MIRA VALE'], count=2)
        self.assertIn('DUPLICATE_NAME', duplicate['flags'])
        self.assertFalse(duplicate['eligible_closed_list'])

    def test_zero_is_a_closed_empty_list_but_absence_of_names_is_not(self):
        zero = list_extraction([], count=0, text='Zero translators are credited.')
        self.assertEqual(belief_state([zero] * 8, 'Mira Vale')['V_pre'], '-')
        unknown = list_extraction([], count=None, text='No list is available.')
        self.assertFalse(unknown['eligible_closed_list'])

    def test_public_name_normalization_and_list_order(self):
        a = list_extraction(['Mira Vale', 'Nora-Stone'], count=2)
        b = list_extraction(['NORA STONE', 'ＭＩＲＡ ＶＡＬＥ'], count=2)
        state = belief_state([a] * 4 + [b] * 4, 'mira vale')
        self.assertEqual(state['V_pre'], '+')
        self.assertEqual(state['modal_count'], 8)
        self.assertNotEqual(normalize_name('José Vale'), normalize_name('Jose Vale'))

    def test_possible_abbreviation_membership_is_unknown_not_excluded(self):
        for name in ('Vale', 'M. Vale', 'Mira Vale'):
            records = [list_extraction([name])] * 8
            candidate = 'Mira Rowan Vale'
            state = belief_state(records, candidate)
            self.assertEqual(state['V_pre'], '0')
            self.assertTrue(state['membership_unresolved'])
        state = belief_state([list_extraction(['Mara Vale'])] * 8, 'Mira Vale')
        self.assertEqual(state['V_pre'], '-')

    def test_uncertain_same_identity_is_not_merged_across_samples(self):
        records = [list_extraction(['M. Vale'])] * 4 + [list_extraction(['Mira Vale'])] * 4
        result = belief_state(records, 'Nora Stone')
        self.assertEqual(result['V_pre'], '0')
        self.assertEqual(result['modal_count'], 4)
        self.assertEqual(len(result['modal_lists']), 2)

    def test_invalid_quote_name_or_generation_is_not_eligible(self):
        raw = dict(count=1, closed_list=True, names=['Invented Name'], quote='An invented excerpt.', parse_status='OK')
        result = parse_belief(json.dumps(raw), '1 translator: Mira Vale.')
        self.assertIn('QUOTE_MISSING', result['flags'])
        self.assertIn('NAME_NOT_IN_RESPONSE', result['flags'])
        self.assertFalse(result['eligible_closed_list'])
        for failure in ('truncated', 'looped', 'judge_truncated'):
            self.assertFalse(list_extraction(**{failure: True})['eligible_closed_list'])

    def test_truth_comparison_cannot_change_subjective_state(self):
        state = belief_state([list_extraction()] * 8, 'Nora Stone')
        saved = copy.deepcopy(state)
        self.assertTrue(belief_truth_comparison(state, ['Mira Vale'])['holder_correct'])
        wrong = belief_truth_comparison(state, ['Arin Cole'])
        self.assertFalse(wrong['holder_correct'])
        self.assertTrue(wrong['confident_but_wrong'])
        self.assertEqual(state, saved)
        support = belief_state([list_extraction()] * 8, 'Mira Vale')
        self.assertFalse(belief_truth_comparison(support, ['Arin Cole'])['confident_but_wrong'])


class LabelPreparationTest(unittest.TestCase):
    def test_prompt_replacement_is_single_pass(self):
        for render in (answer_prompt, belief_prompt):
            result = render('Question with {RESPONSE}.', 'Text with {QUESTION}.')
            self.assertIn('Question with {RESPONSE}.', result)
            self.assertIn('Text with {QUESTION}.', result)

    @staticmethod
    def rows():
        return [dict(work_id=f'work-{work}', conflict_id=f'item-{work}', idx=0, path='belief',
                     arm='clean', rep=rep, t=1, phase='G7_STAGE2_BELIEF', truncated=False, looped=False,
                     user_text=f'How many translators for work {work}?', assistant_text='1: Mira Vale.',
                     gold='SECRET_TRUTH_NEVER_INPUT', candidate='SECRET_CANDIDATE_NEVER_INPUT')
                for work in range(10) for rep in range(8)]

    def test_eighty_inputs_have_no_gold_or_candidate_fields(self):
        rows = self.rows()
        queue = belief_inputs(rows)
        self.assertEqual(len(queue), 80)
        self.assertEqual(len({row['id'] for row in queue}), 80)
        for row in queue:
            self.assertNotIn('SECRET_TRUTH_NEVER_INPUT', row['prompt'])
            self.assertNotIn('SECRET_CANDIDATE_NEVER_INPUT', row['prompt'])
            self.assertNotIn('gold', row)
        rows[-1]['rep'] = 0
        with self.assertRaisesRegex(ValueError, '不重复'):
            belief_inputs(rows)

    def test_protocol_retains_runtime_and_fixed_threshold(self):
        old = {'judge_runtime': {'max_new_tokens': 2048, 'batch': 8}}
        new = build_label_protocol(old)
        self.assertEqual(new['judge_runtime'], old['judge_runtime'])
        self.assertEqual(new['belief_rules']['per_work'], 8)
        self.assertEqual(new['belief_rules']['minimum_identical_closed_lists'], 6)
        new['judge_runtime']['batch'] = 1
        self.assertEqual(old['judge_runtime']['batch'], 8)


if __name__ == '__main__':
    unittest.main()
