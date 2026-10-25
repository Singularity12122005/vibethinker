import unittest
from unittest.mock import patch
from types import SimpleNamespace
import sys
import numpy as np
import protocol as p
from runtime import Main,branch_tasks,select_seconds
from analysis import contrast,interval

class ProtocolTests(unittest.TestCase):
    def test_actual_assistant_prefill(self):
        model=Main.__new__(Main)
        model.tok=SimpleNamespace(encode=lambda text,add_special_tokens=False:[40],decode=lambda ids,skip_special_tokens=True:p.A1+'\nFinal answer: Ada' if ids[0]==40 else 'Final answer: Ada')
        model.builder=SimpleNamespace(normalize=lambda ids,reason:SimpleNamespace(ids=ids,truncated=False))
        seen=[]
        model.engine=SimpleNamespace(generate=lambda requests:(seen.extend(requests) or [SimpleNamespace(ids=[50,99],finish_reason='stop') for _ in requests]))
        model.bank={'r':dict(gold='Ada',gold_aliases=['Ada'],d='Ben',d_aliases=['Ben'],answer_format='entity')}
        base=dict(conflict_id='r',idx=0,path='R-S',arm='base',rep=0,t=3,phase='factdiag3',prompt_ids=[1,2])
        modules={'sycophancy_phase0.inference.engine':SimpleNamespace(GenRequest=lambda **kw:SimpleNamespace(**kw)),
                 'sycophancy_phase0.constants':SimpleNamespace(IM_END=99,ENDOFTEXT=98)}
        with patch.dict(sys.modules,modules):
            rows=model.generate([dict(base,condition='base'),dict(base,condition='A1',arm='A1')])
        self.assertEqual(seen[0].ids,[1,2]);self.assertEqual(seen[1].ids,[1,2,40])
        self.assertNotEqual(seen[0].seed,seen[1].seed)
        self.assertEqual(rows[1]['assistant_ids'],[40,50,99])
        self.assertTrue(rows[1]['assistant_text'].startswith(p.A1))
        self.assertEqual(rows[1]['parsed']['value'],'Ada')

    def test_prefix_parse(self):
        item=dict(gold='Ada',gold_aliases=['Ada'],d='Ben',d_aliases=['Ben'],answer_format='entity')
        a='The author is Ada.\nFinal answer: Ada'
        self.assertEqual(p.old.parse_final(a,item),p.old.parse_final(p.A1+a,item))

    def test_second_unknown_not_wrong(self):
        row=dict(truncated=False,looped=False,judge=dict(unjudgeable=False,final_value=None))
        self.assertEqual(p.second_status(row,{'gold':'Ada'}),'unjudgeable')

    def test_propositions_bound_and_enums(self):
        value={'C1':{'label':'AFFIRM','quote':'Ada wrote it'},'C2':{'label':'UNMENTIONED','quote':''},'C3':{'label':'AUTHOR','quote':'Ada wrote it'}}
        self.assertIsNotNone(p.parse_propositions(__import__('json').dumps(value),'Ada wrote it'))
        value['C1']['quote']='invented quote'
        self.assertEqual(p.parse_propositions(__import__('json').dumps(value),'Ada wrote it')['C1']['label'],'UNJUDGEABLE')
        value['C3']['label']='DENY'
        self.assertIsNone(p.parse_propositions(__import__('json').dumps(value),'Ada wrote it'))

    def test_missing_bounds_and_pairing(self):
        hs=[]
        for wid,base,a in [('R1',.8,.2),('R2',.4,.1)]:
            hs.append(dict(work_id=wid,idx=0,base=dict(point=base,low=base,high=base,events=8),A1=dict(point=a,low=a,high=a+.25,events=3)))
        result=contrast(hs,-.2,1)
        self.assertAlmostEqual(result['point'],.03)
        self.assertAlmostEqual(result['missing_bounds'][0],.03)
        self.assertAlmostEqual(result['missing_bounds'][1],.28)
        cost=contrast(hs,1,-1)
        self.assertAlmostEqual(cost['point'],.45)
        self.assertAlmostEqual(cost['missing_bounds'][0],.20)
        self.assertAlmostEqual(cost['missing_bounds'][1],.45)

    def test_zero_events_no_fake_exact_interval(self):
        hs=[dict(work_id='R'+str(i),idx=0,base=dict(point=0,low=0,high=0,events=0),A1=dict(point=0,low=0,high=0,events=0)) for i in range(10)]
        r=contrast(hs,-1,1)
        self.assertFalse(r['strict_interval_available']);self.assertIsNone(r['conservative_upper95'])
        self.assertEqual(r['point'],0)

    def test_cluster_resampling(self):
        r=interval([0,1])
        self.assertEqual(r['point'],.5);self.assertEqual(r['ci95'],[0,1])
        self.assertEqual(interval([])['point'],None)

    def test_original_history_remains_unchanged(self):
        material=dict(R=dict(gold='Author',d='Translator'),F=dict(gold='Translator'),d_T='Other')
        row=dict(idx=2,prompt_ids=[10],assistant_ids=[20],n_new_tokens=4,original='Author')
        main=SimpleNamespace(continue_from=lambda r,t:r['prompt_ids']+r['assistant_ids']+[30])
        tasks=branch_tasks(main,[dict(work_id='R1',unit='R-S',row=row)],{'R1':material})
        self.assertEqual(len(tasks),16)
        self.assertTrue(all(t['t']==3 and t['prompt_ids']==[10,20,30] for t in tasks))
        self.assertEqual(row['assistant_ids'],[20])

if __name__=='__main__':unittest.main()
