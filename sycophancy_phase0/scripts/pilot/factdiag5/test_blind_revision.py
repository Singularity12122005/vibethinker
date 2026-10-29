"""第五批独立复核的合成覆盖、盲化、一次提交和分标签质量测试。"""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

from . import blind_revision as b
from . import blind_revision_access as access
from .test_judge_core import synthetic
from .judge_core import build_inputs
from ..factdiag7.stage2_revision import construct_inputs
from ..factdiag7.relation_protocol_v3 import PROMPT


def fixture():
    material, rows, prereg, _, relation_material = synthetic()
    protocol = dict(version='stage2-relations-v3', prompt=PROMPT)
    legacy = build_inputs(material, rows, prereg)
    relations = construct_inputs(protocol, relation_material, [], [], rows, material)['batch5']
    return dict(material=material, rows=rows, legacy=legacy, relation_queue=relations, protocol=protocol)


def complete_labels(blind, key, data):
    rows = {r['request_id']: r for r in data['rows']}; bindings = {r['blind_id']: r for r in key['records']}
    labels = {}
    for card in blind['records']:
        value = deepcopy(card['submission']); value['review_complete'] = True
        row = rows[bindings[card['blind_id']]['request_id']]; annotation = value['annotations']
        annotation['supported_answer'] = row['parsed']['value']; annotation['explicit'] = 'EXPLICIT'
        if 'evidence_disputed' in annotation:
            annotation['evidence_disputed'] = 'YES'
        if 'status' in annotation:
            annotation['status'] = 'CANNOT_VERIFY'
        if 'propositions' in annotation:
            annotation['propositions'] = {k: dict(label='UNMENTIONED' if k != 'C3' else 'UNJUDGEABLE', quote='')
                                           for k in ('C1', 'C2', 'C3')}
        if 'relations_v3' in annotation:
            annotation['relations_v3']['extraction'] = dict(parse_status='OK', claims=[], mention='ABSENT',
                verification_claim='NONE', generic_description=False, reported_attribution=False)
        labels[card['blind_id']] = value
    return labels


def machine_data(data):
    data = deepcopy(data); data['legacy_saved'] = {}; data['original'] = {}
    for kind, queue in data['legacy']['queues'].items():
        for q in queue:
            if kind == 'legacy_stance':
                value = dict(missing=False, stance='ORIG', explicit='EXPLICIT')
            elif kind == 'legacy_propositions':
                value = dict(missing=False, propositions={k: dict(label='AFFIRM' if k != 'C3' else 'AUTHOR', quote='synthetic')
                                                           for k in ('C1', 'C2', 'C3')})
            else:
                value = dict(missing=False, evidence_disputed=True)
            data['legacy_saved'][q['id']] = dict(input_sha256=q['input_sha256'], result=value, completion='returned')
    for q in data['relation_queue']:
        data['original'][q['id']] = dict(input_sha256=q['input_sha256'], completion='returned',
            extraction=dict(parse_status='OK', claims=[], mention='ABSENT', verification_claim='NONE', extraction_flags=[]))
    data.update(reprompt={}, selected_reprompt=set())
    return data


class FifthBlindRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = fixture()
        cls.blind, cls.key = b.construct(**cls.data)

    def test_quota_sampling_is_stable_shares_rows_and_preserves_shortages(self):
        pools = dict(pools=[dict(quota_id='b', required=2, available=1, request_ids=['one']),
                           dict(quota_id='a', required=2, available=3, request_ids=['three', 'two', 'one'])])
        first = b.choose(pools)
        reversed_pools = deepcopy(pools); reversed_pools['pools'].reverse()
        for p in reversed_pools['pools']:
            p['request_ids'].reverse()
        self.assertEqual(first, b.choose(reversed_pools))
        self.assertEqual(first[0]['b'], ['one'])
        self.assertEqual(set(first[1]), set(first[0]['a'] + first[0]['b']))
        details = {r['quota_id']: r for r in self.key['coverage']['details']}
        self.assertEqual(details['identity_5_1']['requested'], 10)
        self.assertEqual(details['evidence_disputed']['requested'], 20)
        self.assertEqual(details['status_5_5']['requested'], 20)
        self.assertTrue(any(r['shortage'] > 0 for r in details.values()))
        self.assertFalse(any('5.2' in key or 'R1doubleprime' in key for key in details))

    def test_cards_omit_truth_and_machine_labels_but_preserve_original_context(self):
        rows = {r['request_id']: r for r in self.data['rows']}
        keys = {r['blind_id']: r for r in self.key['records']}
        relation = {q['response_id']: q for q in self.data['relation_queue']}
        for card in self.blind['records']:
            row = rows[keys[card['blind_id']]['request_id']]
            self.assertEqual(card['response'], row['assistant_text'])
            self.assertEqual(card['user_message'], row['user_text'])
            self.assertEqual(card['system_record'], row['system_record'])
            self.assertEqual(card['forced_prefix'], row['forced_prefix'])
            self.assertFalse({'request_id', 'work_id', 'cell', 'arm', 'unit', 'parsed', 'gold', 'item', 'person'} & card.keys())
            text = json.dumps(card['instructions'], ensure_ascii=False)
            self.assertNotIn('Correct answer under the current conditions:', text)
            self.assertNotIn('stipulated true', text)
            if row['request_id'] in relation:
                q = relation[row['request_id']]
                self.assertEqual(card['instructions']['relations_v3']['prompt'], q['prompt'])
            else:
                self.assertNotIn('relations_v3', card['instructions'])

    def test_relation_scope_and_question_role_cannot_be_switched(self):
        altered = deepcopy(self.data)
        altered['relation_queue'][0]['kind'] = 'GOLD'
        with self.assertRaises(ValueError):
            b.construct(**altered)
        altered = deepcopy(self.data)
        q = altered['relation_queue'][0]
        q['item']['target_relation'] = 'TRANSLATOR' if q['item']['target_relation'] == 'AUTHOR' else 'AUTHOR'
        with self.assertRaises(ValueError):
            b.construct(**altered)
        altered = deepcopy(self.data); altered['relation_queue'][0]['prompt'] += '\nAdditional hint.'
        with self.assertRaises(ValueError):
            b.construct(**altered)

    def test_access_reads_only_cards_and_once_submissions(self):
        labels = complete_labels(self.blind, self.key, self.data)
        with TemporaryDirectory() as folder:
            path = Path(folder)
            b.save_new(path / b.BLIND, self.blind)
            # 专用读取即使同目录有私有真值文件，也不打开它。
            (path / b.KEY).write_text('THIS MUST NOT BE READ', encoding='utf-8')
            with patch.object(access, 'load', wraps=access.load) as reader:
                first = access.access(path, 'read', offset=0, count=1)[0]
            self.assertEqual(first, self.blind['records'][0])
            self.assertEqual([call.args[0].name for call in reader.call_args_list], [b.BLIND])
            label = labels[first['blind_id']]
            status = access.access(path, 'submit', incoming=[label])
            self.assertEqual(status['done'], 1)
            self.assertEqual(access.access(path, 'submit', incoming=[label])['done'], 1)
            changed = deepcopy(label); changed['annotations']['supported_answer'] = 'Changed answer'
            with self.assertRaises(RuntimeError):
                access.access(path, 'submit', incoming=[changed])
            self.assertEqual(access.access(path, 'status')['completed_ids'], [first['blind_id']])

    def test_submission_requires_completed_all_labels_and_exact_person(self):
        card = next(r for r in self.blind['records'] if 'relations_v3' in r['instructions'])
        value = deepcopy(card['submission'])
        with self.assertRaises(ValueError):
            access.validate_submission(card, value)
        value['review_complete'] = True
        access.validate_submission(card, value)  # 显式完成后null是缺测，不是阴性。
        altered = deepcopy(value); altered['annotations']['relations_v3']['candidate'] = 'Another Person'
        with self.assertRaises(ValueError):
            access.validate_submission(card, altered)
        altered = deepcopy(value); del altered['annotations']['explicit']
        with self.assertRaises(ValueError):
            access.validate_submission(card, altered)

    def test_quality_separates_all_label_families_and_never_emits_effects(self):
        labels = complete_labels(self.blind, self.key, self.data)
        data = machine_data(self.data)
        with patch.object(b.relations_v3, 'aggregate', wraps=b.relations_v3.aggregate) as aggregate:
            report = b.compare_data(self.blind, self.key, labels, data)
        for name in ('identity', 'stance', 'explicit', 'C1', 'C2', 'C3', 'evidence_disputed', 'status'):
            self.assertIn(name, report['labels'])
        self.assertEqual(report['labels']['identity']['conservative_agreement'], 1)
        self.assertEqual(report['labels']['explicit']['conservative_agreement'], 1)
        self.assertEqual(report['labels']['evidence_disputed']['conservative_agreement'], 1)
        self.assertLess(report['labels']['stance']['conservative_agreement'], 1)
        self.assertEqual(report['labels']['C1']['conservative_agreement'], 0)
        self.assertEqual(report['labels']['C3']['both_determined'], 0)
        self.assertFalse(report['automatic_release'])
        self.assertFalse(report['relation_population_rates_computed'])
        self.assertEqual(set(report['relation_quality']), set(b.COLUMNS))
        self.assertTrue(all(len(call.args) == 1 and call.kwargs['execution_no_tools'] for call in aggregate.call_args_list))
        text = json.dumps(report, ensure_ascii=False)
        for forbidden in ('machine_events', 'independent_events', 'conservative_interval', 'MIXED_anchor":', '"confusion'):
            self.assertNotIn(forbidden, text)
        self.assertEqual(data['rows'], self.data['rows'])

    def test_missing_labels_retain_full_denominators_and_no_reprompt(self):
        labels = complete_labels(self.blind, self.key, self.data)
        data = machine_data(self.data)
        for value in labels.values():
            for name in value['annotations']:
                if name == 'relations_v3':
                    value['annotations'][name]['extraction'] = 'not json'
                elif name in ('explicit', 'status'):
                    value['annotations'][name] = 'INVALID_LABEL'
                else:
                    value['annotations'][name] = None
        report = b.compare_data(self.blind, self.key, labels, data)
        for stats in report['labels'].values():
            self.assertEqual(stats['both_determined'], 0)
            self.assertEqual(stats['conservative_agreement'], 0)
        for column in b.COLUMNS:
            self.assertEqual(report['relation_quality'][column]['W_false']['planned'], report['relation_views'])
            self.assertEqual(report['relation_quality'][column]['W_false']['conservative_agreement'], 0)
        del labels[next(iter(labels))]
        with self.assertRaises(ValueError):
            b.compare_data(self.blind, self.key, labels, data)

    def test_prepare_existing_pair_never_resamples_and_rejects_half_saved_pair(self):
        with TemporaryDirectory() as folder:
            path = Path(folder)
            b.save_new(path / b.BLIND, self.blind)
            with patch.object(b, 'remote_paths', return_value=(path, path, path)), \
                 patch.object(b, 'inputs', side_effect=AssertionError('不得重读或重抽')):
                with self.assertRaises(RuntimeError):
                    b.prepare(path)
                b.save_new(path / b.KEY, self.key)
                self.assertTrue(b.prepare(path)['reused'])


if __name__ == '__main__':
    unittest.main()
