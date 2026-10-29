from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from .intervention8_review import assemble, write_review, EVENT_FIELDS, STEM


class FullReviewExportTest(unittest.TestCase):
    def fixture(self):
        cards = []; inputs = {}; strong = {}; drafts = {}; previous = {}
        for i in range(110):
            bid = f'R-{i:03}'; rid = f'response-{i}'
            views = [dict(candidate='译者', roles=['D', 'T'], input_id=f'{i}-T'),
                     dict(candidate='作者', roles=['A'], input_id=f'{i}-A')]
            if i >= 107:
                views[0]['roles'] = ['T']
                views.append(dict(candidate='候选', roles=['D'], input_id=f'{i}-D'))
            card = dict(human_id=bid, response_id=rid, work_id=str(i % 10), idx=i,
                        arm='none', cell='5.5' if i >= 100 else 'M-right', unit='R-S', views=views,
                        question='原问题', user_message='用户证据 <script>保留原文</script>',
                        fixed_context='固定前缀', response='完整正文', materials={'冻结材料':'原样'})
            cards.append(card)
            previous[rid] = dict(current_answer='前轮姓名')
            for v in views:
                q = dict(person={'name':v['candidate']}, response_id=rid, input_sha256=v['input_id'],
                         prompt_sha256=v['input_id'], **{k:card[k] for k in ('response','user_message','fixed_context')})
                inputs[v['input_id']] = q
                strong[v['input_id']] = dict(completion='returned', raw='原始提取',
                                            input_sha256=q['input_sha256'], prompt_sha256=q['prompt_sha256'])
            draft = dict(human_id=bid, human_review_complete=False,
                         views=[dict(candidate=v['candidate'], roles=v['roles'], 人工命题=[]) for v in views],
                         **{k:None for k in EVENT_FIELDS})
            draft['W_target'] = 1
            for stage in ('first','second'):
                drafts[bid+'|draft|'+stage] = dict(completion='returned', draft_valid=True, draft=deepcopy(draft))
        blind = []
        for card in cards[:20]:
            row = deepcopy(drafts[card['human_id']+'|draft|second']['draft'])
            row.update(work_id=card['work_id'], history_index=card['idx'], arm=card['arm'],
                       cell=card['cell'], unit=card['unit'], W_target=0)
            blind.append(row)
        plan = dict(records=deepcopy(cards), blind20=[r['human_id'] for r in blind])
        received = dict(human_review_complete=True, confirmation_source='用户明确确认',
                        original_document={'records':blind})
        return [plan, cards, inputs, strong, received, previous, {}]

    def test_preserves_first_blind_and_context_without_mutating_sources(self):
        args = self.fixture(); before = deepcopy(args)
        reading, document = assemble(*args)
        self.assertEqual(args, before)
        self.assertEqual(len(document['records']), 110)
        self.assertTrue(all(r['human_review_complete'] is False for r in document['records']))
        self.assertIsNone(document['records'][0]['W_target'])
        self.assertIsNone(document['records'][20]['W_target'])
        self.assertTrue(all(not v['人工命题'] for r in document['records'] for v in r['views']))
        self.assertIn('前轮姓名', reading)
        self.assertIn('&lt;script&gt;保留原文&lt;/script&gt;', reading)
        self.assertNotIn('<script>', reading)
        self.assertIn('执行方只提供材料', reading)
        self.assertNotIn('第二遍草稿', reading)

    def test_incomplete_or_misbound_inputs_and_drafts_never_export(self):
        for target in ('blind', 'missing_view', 'binding', 'previous'):
            with self.subTest(target=target):
                args = self.fixture()
                if target == 'blind': args[4]['human_review_complete'] = False
                if target == 'missing_view': del args[3]['0-T']
                if target == 'binding': args[3]['0-T']['prompt_sha256'] = '错误绑定'
                if target == 'previous': del args[5]['response-100']
                with self.assertRaises(ValueError): assemble(*args)

    def test_existing_user_labels_are_never_overwritten(self):
        reading, document = assemble(*self.fixture())
        with TemporaryDirectory() as temp:
            first = write_review(temp, reading, document)
            self.assertFalse(first['labels_preserved'])
            file = Path(temp)/(STEM+'_labels.json')
            user = json.loads(file.read_text('utf-8')); user['records'][0]['human_review_complete'] = True
            file.write_text(json.dumps(user, ensure_ascii=False), encoding='utf-8')
            original = file.read_bytes()
            second = write_review(temp, reading+'\n', document)
            self.assertTrue(second['labels_preserved'])
            self.assertEqual(file.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
