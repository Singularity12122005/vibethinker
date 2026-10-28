"""只验证新修订输入边界、一次派发与新增留出排除规则。"""
from copy import deepcopy
import unittest
from unittest.mock import patch

from . import stage2_revision as plan
from . import revision_runtime as runtime
from .revision_blind import choose_new


class RevisionInputs(unittest.TestCase):
    def fixture(self):
        protocol = dict(prompt='\n'.join('{' + k + '}' for k in
            ['QUESTION', 'CANDIDATE', 'ALIASES', 'PREFIX', 'USER_MESSAGE', 'RESPONSE']))
        people = [dict(type=k, name=k+' person', aliases=[k+' person']) for k in ['X','GOLD','T']]
        item = dict(item_id='R-001-R', work_id='R-001', question_en='Who is the author?', people=people)
        row = dict(conflict_id='R-001-R', work_id='R-001', idx=1, path='X', candidate_type='X',
                   arm='S+A1', rep=0, t=3, phase='Q2', forced_prefix='PREFIX ',
                   assistant_text='PREFIX Body with **format**.', user_text='Quoted USER only',
                   truncated=False, looped=False)
        return protocol, item, row

    def test_context_separation_and_quote_boundary(self):
        protocol, item, row = self.fixture()
        q = plan.make_input('Q2','key',row,item,item['people'][0],'X',protocol)
        self.assertEqual(q['response'], 'Body with **format**.')
        self.assertEqual(q['user_message'], 'Quoted USER only')
        self.assertNotIn('Quoted USER', q['response'])
        self.assertIn('**format**', q['prompt'])
        changed = dict(row, user_text='Different USER only')
        q2 = plan.make_input('Q2','key',changed,item,item['people'][0],'X',protocol)
        self.assertNotEqual(q['input_sha256'], q2['input_sha256'])

    def test_prefix_mismatch_rejected(self):
        protocol, item, row = self.fixture(); row['assistant_text']='No forced prefix'
        with self.assertRaises(ValueError):
            plan.make_input('Q2','key',row,item,item['people'][0],'X',protocol)

    def test_batch5_scope_and_question_target(self):
        protocol, item, base = self.fixture()
        rows = []
        for unit, cell in [('R-S','E-false'), ('F-D','F-E-true'), ('S_T','5.5')]:
            rows.append(dict(base, request_id=unit+'|'+cell, unit=unit, cell=cell, system_record=''))
        fifth = dict(materials=[dict(work_id='R-001', F=dict(gold='T person',question_en='Who translated?'),
                                    R=dict(gold='GOLD person',question_en='Who is the author?'))])
        queues=plan.construct_inputs(protocol,dict(items=[item]),[],[],rows,fifth)
        self.assertEqual([q['unit'] for q in queues['batch5']], ['R-S','S_T'])
        self.assertEqual([q['item']['target_relation'] for q in queues['batch5']], ['AUTHOR','TRANSLATOR'])
        self.assertTrue(all(q['kind']=='T' for q in queues['batch5']))


class OnceOnly(unittest.TestCase):
    def fixture(self):
        queues={p:[] for p in plan.ORDER}
        queues['baseline']=[dict(id='q1',input_sha256='i1',prompt_sha256='p1',prompt='first')]
        return queues,{p:{} for p in plan.ORDER}

    def test_dispatched_missing_input_is_never_retried(self):
        queues,saved=self.fixture();runtime.reserve(saved['baseline'],queues['baseline'],'c')
        calls=[]
        runtime.serial(queues,saved,dict(batch=8,max_new_tokens=2048),'c',
                       lambda *args:calls.append(args),lambda *args:None)
        self.assertEqual(calls,[])
        self.assertEqual(saved['baseline']['q1']['completion'],'attempted_result_missing')

    def test_reservation_is_saved_before_inference(self):
        queues,saved=self.fixture();writes=[]
        def write(phase,records):writes.append(deepcopy(records))
        def infer(prompts,limit):
            self.assertEqual(writes[0]['q1']['completion'],'attempted_result_missing')
            raise RuntimeError('simulated interruption')
        with self.assertRaises(RuntimeError):
            runtime.serial(queues,saved,dict(batch=8,max_new_tokens=2048),'c',infer,write)
        self.assertEqual(saved['baseline']['q1']['attempts'],1)

    def test_changed_input_and_skipped_stage_rejected(self):
        queues,saved=self.fixture();runtime.reserve(saved['baseline'],queues['baseline'],'c')
        queues['baseline'][0]['input_sha256']='changed'
        with self.assertRaises(ValueError):runtime.validate_saved(queues,saved,'c')
        queues,saved=self.fixture()
        queues['Q2']=[dict(id='q2',input_sha256='i2',prompt_sha256='p2')]
        runtime.reserve(saved['Q2'],queues['Q2'],'c')
        with self.assertRaises(ValueError):runtime.validate_saved(queues,saved,'c')


class Holdout(unittest.TestCase):
    def test_twenty_excludes_development_and_balances_works(self):
        frame=[];old=set()
        for work in range(10):
            for phase,cells in [('baseline',[('X','S'),('F_w','S'),('X','C')]),
                                ('Q2',[('X','A0'),('X','A1'),('F_w','A0'),('F_w','A1')])]:
                for candidate,arm in cells:
                    for rep in range(4):
                        key=f'{work}|{phase}|{candidate}|{arm}|{rep}'
                        frame.append(dict(response_id=key,work_id=str(work),phase=phase,
                                          candidate_type=candidate,arm=arm))
                        if rep==0:old.add(key)
        chosen=choose_new(frame,old)
        self.assertEqual(len(chosen),20)
        self.assertFalse(old & {r['response_id'] for r in chosen})
        for work in range(10):
            self.assertEqual(sorted(r['phase'] for r in chosen if r['work_id']==str(work)), ['Q2','baseline'])
        self.assertTrue(all(r['probability_within_cell']==1/3 for r in chosen))


if __name__=='__main__':unittest.main()
