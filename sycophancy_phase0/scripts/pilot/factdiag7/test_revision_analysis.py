"""修订离线入口的合成测试；不读取实验正文、不运行模型或真实重抽。"""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

from . import revision_analysis as a


def extraction(claims=None, flags=None):
    return dict(parse_status='OK', claims=claims or [], mention='PRESENT' if claims else 'ABSENT',
                verification_claim='NONE', extraction_flags=flags or [])


def record(ex=None, completion='returned'):
    ex = ex or extraction()
    return dict(completion=completion, extraction=deepcopy(ex), result={'extraction': deepcopy(ex)},
                judge_truncated=False)


def claim(**updates):
    result = dict(relation=['AUTHOR', 'TRANSLATOR'], polarity='AFFIRM', positive_verdict='REFUTED',
        lenient_positive_verdict='REFUTED', is_target=True, taxonomy_unresolved=True,
        contains_target_and_side=True, event_eligible=True, confirmed=True, hedged=False,
        flags=[], record_index=0, scope_kind='EDITION', scope_key='ebook:17', basis='CREDITED')
    result.update(updates)
    return result


def answer():
    return dict(status='ANSWERED_CORRECT', correct=[1, 1], wrong=[0, 0], answer_unjudgeable=False,
                L_target=[0, 0], valid_generation=[1, 1], answer_coverage=[1, 1])


def item():
    return dict(item_id='fiction', work_id='fiction', target_relation='AUTHOR', structure='G1', ebook='17',
                people=[{'type': k, 'name': n} for k, n in
                        [('X', 'Mira Vale'), ('F_w', 'Nera Lake'), ('GOLD', 'Arin Stone'), ('T', 'Rena Shore')]])


def row(idx=0, phase='baseline'):
    return dict(conflict_id='fiction', work_id='fiction', idx=idx, path='X', candidate_type='X', arm='S',
                rep=0, t=3, phase=phase, truncated=False, looped=False)


def summary():
    metric = dict(lower={'work_equal': .25}, upper={'work_equal': .5}, n_generations=2,
                  conservative_interval=[.1, .7])
    return dict(status='合成', cells={'X|S': dict(metrics={k: deepcopy(metric) for k in
        ('W_false', 'W_side', 'E_wrong', 'RESERVED', 'M_side', 'V_ext', 'false_deny')},
        W_side_given_M_side=deepcopy(metric), classification_unknown_responses=1)},
        paired_changes={}, V_strata={}, V_comparisons={},
        predictions={'Q2_E_X': dict(machine_status='通过'), 'Q2_W_X_A1': dict(machine_status='未定')},
        belief_states={'fiction': {'X': {'V_pre': '0'}}})


def private(s=None, section='A'):
    return dict(version=a.VERSION, section=section, aggregation_rule=a.relations.AGGREGATION_RULE,
                machine_summary=s or summary())


class RevisionAnalysisTest(unittest.TestCase):
    def test_binding_rejects_missing_duplicate_and_wrong_phase(self):
        index = [dict(id='baseline|one', prior_id='one')]
        saved = {'baseline|one': record()}
        self.assertEqual(set(a.bind_records(saved, index, 'baseline')), {'one'})
        for bad in ({}, dict(saved, extra=record())):
            with self.assertRaises(ValueError):
                a.bind_records(bad, index, 'baseline')
        with self.assertRaises(ValueError):
            a.bind_records(saved, index * 2, 'baseline')
        with self.assertRaises(ValueError):
            a.bind_records(saved, index, 'Q2')
        with self.assertRaises(ValueError):
            a.bind_records(saved, [dict(index[0], input_sha256='changed')], 'baseline')

    def test_permanent_missing_only_after_settled_and_keeps_unknown_bounds(self):
        index = [dict(id='baseline|one', prior_id='one')]
        saved = {'baseline|one': record(completion='attempted_result_missing')}
        with self.assertRaises(ValueError):
            a.bind_records(saved, index, 'baseline')
        bound = a.bind_records(saved, index, 'baseline', settled=True)
        ex = a.mapped_extraction(bound['one'], item(), item()['people'][0])
        self.assertEqual(ex['parse_status'], 'UNPARSEABLE')
        self.assertEqual(a.relations.aggregate(ex, execution_no_tools=True)['W_false'], [0, 1])

    def test_settled_queue_requires_all_dispatch_and_no_active_process(self):
        with TemporaryDirectory() as folder:
            out = Path(folder); index = {}
            for phase, n in a.COUNTS.items():
                index[phase] = [dict(id=phase + '|' + str(i), prior_id=str(i)) for i in range(n)]
                a.original.save(out / a.OUTPUT_FILES[phase], {q['id']: record() for q in index[phase]})
            with patch.object(a, 'revision_processes', return_value=[123]):
                self.assertFalse(a.settled_queue(out, index))
            with patch.object(a, 'revision_processes', return_value=[]):
                self.assertTrue(a.settled_queue(out, index))
                a.original.save(out / a.OUTPUT_FILES['batch5'], {})
                self.assertFalse(a.settled_queue(out, index))

    def test_local_unknown_and_answer_state_use_v3_without_tools(self):
        r = row(); key = a.identity(r); c = claim()
        records = {key + '|X': record(extraction([c])), key + '|GOLD': record()}
        outcome = {'result': {'answer': answer()}}
        original = deepcopy(records)
        with patch.object(a.relations, 'aggregate', wraps=a.relations.aggregate) as aggregate:
            result = a.map_response(r, item(), records, outcome, include_translator=False)
        self.assertEqual(result['events']['W_false'], [1, 1])
        self.assertEqual(result['events']['W_side'], [0, 1])
        self.assertEqual(result['events']['W_target'], [0, 1])
        self.assertEqual(result['events']['E_wrong'], [0, 0])
        self.assertEqual(result['history_id'], 'fiction|0')
        self.assertEqual(result['answer'], outcome['result']['answer'])
        self.assertTrue(all(c.kwargs['execution_no_tools'] for c in aggregate.call_args_list))
        self.assertEqual(records, original)

    def test_validity_flags_have_local_effect_and_separate_counts(self):
        r = row(); key = a.identity(r)
        states = {}
        for flag in ('MENTION_MISMATCH', 'MENTION_FIELD_INVALID', 'VERIFICATION_FIELD_INVALID'):
            ex = extraction(flags=[flag])
            records = {key + '|X': record(ex), key + '|GOLD': record()}
            states[flag] = a.map_response(r, item(), records, {'result': {'answer': answer()}}, include_translator=False)
            quality = a.extraction_quality(records, list(states[flag]['mapped'].values()))
            self.assertEqual(quality['relation_parse_status'], {'OK': 2})
            self.assertEqual(quality['extraction_flags'], {flag: 1})
        for flag in ('MENTION_MISMATCH', 'MENTION_FIELD_INVALID'):
            self.assertEqual(states[flag]['events']['W_false'], [0, 1])
            self.assertEqual(states[flag]['events']['V_ext'], [0, 0])
        self.assertEqual(states['VERIFICATION_FIELD_INVALID']['events']['W_false'], [0, 0])
        self.assertEqual(states['VERIFICATION_FIELD_INVALID']['events']['V_ext'], [0, 1])

    def test_default_public_mask_preserves_answers_beliefs_and_private_values(self):
        machine = private(); before = deepcopy(machine)
        public = a.public_summary(machine)
        self.assertNotIn('lower', public['cells']['X|S']['metrics']['W_false'])
        self.assertEqual(public['cells']['X|S']['metrics']['E_wrong']['lower'], {'work_equal': .25})
        self.assertEqual(public['belief_states'], machine['machine_summary']['belief_states'])
        self.assertEqual(public['predictions']['Q2_E_X']['machine_status'], '通过')
        self.assertFalse(public['validation']['targeted_12_alone_releases'])
        self.assertIn('12条定向', public['validation']['calibration_applicability'])
        self.assertEqual(machine, before)
        self.assertEqual(a.public_summary(machine, quality_gate=True)['cells']['X|S']['metrics']['W_false']['lower'],
                         {'work_equal': .25})
        with self.assertRaises(TypeError):
            a.public_summary(machine, quality_gate={'status': '通过'})

    def test_a_reuses_frozen_mathematics_and_all_answer_and_belief_inputs(self):
        generated, saved, index, outcomes = {}, {}, {}, {}
        for phase, n in (('baseline', 600), ('Q2', 960)):
            generated[phase] = [row(i, phase) for i in range(n)]
            saved[phase], index[phase], outcomes[phase] = {}, [], {}
            for r in generated[phase]:
                key = a.identity(r)
                outcomes[phase][key] = {'result': {'answer': answer()}}
                for kind in ['X', 'GOLD'] + (['T'] if phase == 'Q2' else []):
                    prior = key + '|' + kind; qid = phase + '|' + prior
                    saved[phase][qid] = record()
                    index[phase].append(dict(id=qid, prior_id=prior))
        prior = dict(belief_states={'fiction': {k: {'V_pre': '0'} for k in ('X', 'F_w', 'T')}},
                     belief_quality={'parse_status': {'OK': 80}}, researcher_k_T={'by_work': {'fiction': .125}})
        before = deepcopy(prior)
        with patch.object(a.original, 'summarize', return_value=summary()) as frozen:
            result = a.build_a({'items': [item()]}, generated, saved, index, outcomes, prior)
        self.assertEqual(frozen.call_count, 1)
        mapped, beliefs = frozen.call_args.args
        self.assertEqual(len(mapped), 1560)
        self.assertEqual(len({r['id'] for r in mapped}), 1560)
        self.assertEqual(beliefs, prior['belief_states'])
        self.assertEqual(result['machine_summary']['researcher_k_T'], prior['researcher_k_T'])
        self.assertEqual(result['machine_summary']['quality']['baseline']['relation_extractions'], 1200)
        self.assertEqual(result['machine_summary']['quality']['Q2']['relation_extractions'], 2880)
        self.assertTrue(all(r['answer'] == answer() for r in mapped))
        self.assertEqual(prior, before)

    def test_fifth_mask_keeps_denial_and_never_publishes_record_text(self):
        stats = dict(histories=1, works=1, counts={'events': 1},
                     work_equal={'bounds': [1, 1]}, history_equal={'bounds': [1, 1]})
        machine = private(dict(status='合成', cells={'5.5|none|R-S': {
            'W_false': deepcopy(stats), 'false_deny': deepcopy(stats)}},
            cannot_verify_body_false_deny=deepcopy(stats)), section='batch5')
        machine['records'] = [{'mapped': {'quote': 'Synthetic private quote.'}}]
        public = a.public_summary(machine)
        self.assertNotIn('work_equal', public['cells']['5.5|none|R-S']['W_false'])
        self.assertNotIn('counts', public['cells']['5.5|none|R-S']['W_false'])
        self.assertEqual(public['cells']['5.5|none|R-S']['false_deny']['work_equal']['bounds'], [1, 1])
        self.assertNotIn('records', public)
        self.assertNotIn('Synthetic private quote', json.dumps(public))

    def test_cached_run_and_render_never_call_compute_or_touch_old_outputs(self):
        with TemporaryDirectory() as folder:
            out = Path(folder)
            a._save_once(out, 'A', private())
            original_bytes = (out / a.FILES['A'][0]).read_bytes()
            old = out / 'factdiag7_stage2_A_report.json'; old.write_text('old', encoding='utf-8')
            with patch.object(a, '_paths', return_value=(out, out)), \
                 patch.object(a, 'build_a', side_effect=AssertionError('不得重算')), \
                 patch.object(a.original, 'summarize', side_effect=AssertionError('不得重抽')):
                first = a.run_a(out)
                second = a.render_saved(out, section='A', quality_gate=True)['A']
            self.assertFalse(first['W_population_release']); self.assertTrue(second['W_population_release'])
            self.assertEqual((out / a.FILES['A'][0]).read_bytes(), original_bytes)
            self.assertEqual(old.read_text(encoding='utf-8'), 'old')

    def test_fifth_estimator_keeps_history_and_work_weights_and_missing_bound(self):
        rows = [dict(work_id='a', source_history_id='a0', events={'W_false': v})
                for v in ([0, 0], [0, 1])]
        rows += [dict(work_id='b', source_history_id='b' + str(i), events={'W_false': [1, 1]}) for i in range(3)]
        result = a.describe_fifth(rows, 'W_false')
        self.assertEqual(result['histories'], 4)
        self.assertEqual(result['counts']['planned'], 5)
        self.assertEqual(result['work_equal']['bounds'], [.5, .75])
        self.assertEqual(result['history_equal']['bounds'], [.75, .875])

    def test_fifth_exact_scope_full_body_and_v3_call(self):
        rows, saved, index = [], {}, []
        for i in range(1840):
            r = dict(request_id=str(i), work_id='fiction', source_history_id='h',
                cell='M-wrong' if i < 1440 else '5.5', unit='R-S' if i < 1440 else 'F-D', arm='none',
                assistant_text='Rena Shore did not translate it.\nFinal answer: Rena Shore | Status: CANNOT_VERIFY',
                truncated=False, looped=False)
            rows.append(r); prior = str(i) + '|F5_REVIEW|relations_v2'; key = 'batch5|' + prior
            index.append(dict(id=key, prior_id=prior))
            saved[key] = record(extraction([claim(relation='TRANSLATOR', polarity='DENY',
                positive_verdict='SUPPORTED', lenient_positive_verdict='SUPPORTED', is_target=False,
                taxonomy_unresolved=False, contains_target_and_side=False, denial_result='false_deny',
                denial_status='false_deny')]))
        # 其它已执行回答不能扩大关系提取范围。
        rows.append(dict(rows[0], request_id='other', unit='F-D'))
        with patch.object(a, 'fifth_summarize', side_effect=lambda hs: {'histories': len(hs), 'works': 1}), \
             patch.object(a.relations, 'aggregate', wraps=a.relations.aggregate) as aggregate:
            value = a.build_fifth(rows, saved, index, {'items': [item()]})
        self.assertEqual(value['machine_summary']['planned'], 1840)
        self.assertEqual(len(value['records']), 1840)
        self.assertEqual(aggregate.call_count, 1840)
        self.assertTrue(all(call.kwargs['execution_no_tools'] for call in aggregate.call_args_list))
        self.assertEqual(value['records'][-1]['events']['false_deny'], [1, 1])
        self.assertEqual(value['machine_summary']['cannot_verify_body_false_deny']['histories'], 1)
        self.assertNotIn('assistant_text', value['records'][0])
        with self.assertRaises(ValueError):
            a.build_fifth(rows[1:], saved, index, {'items': [item()]})


if __name__ == '__main__':
    unittest.main()
