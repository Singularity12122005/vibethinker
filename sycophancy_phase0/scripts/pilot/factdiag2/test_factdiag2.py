"""必要正确性检查：分支、冻结话术和缺失统计。"""
import hashlib
from itertools import product
from pathlib import Path
import random
import sys
import unittest
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
from rules import SR3,L3,ROLES,MODE_PROMPT,third,parse_mode,parse_final,event3,raw_final_value
from runtime import choose_first,make_seconds,make_branches,make_fourths,identity,digest,run_tasks,load,save
from metrics import covariance,covariance_bounds,prefix_stats,instance_stats,group_stats
from analysis import branch_outcomes,planned_rate,joint_event,summarize
from control import validate
from specification import preregistration

R=dict(conflict_id='R-001',pool='R',question_en='Who wrote it?',P_g='Author wrote it.',gold='Author',d='Translator',
       gold_aliases=['Author'],d_aliases=['Translator'],answer_format='entity',status='eligible_precalibration')
F={**R,'conflict_id':'F-001','pool':'F','gold':'Translator','d':'Author','gold_aliases':['Translator'],'d_aliases':['Author']}


class FakeMain:
    def continue_from(self,row,text):return row['prompt_ids']+row['assistant_ids']+[sum(text.encode())]


def first(item,idx,value):
    text='Reason.\nFinal answer: '+value
    return dict(conflict_id=item['conflict_id'],pool=item['pool'],idx=idx,path='initial',arm='shared',rep=0,t=1,phase='calibration',
        assistant_text=text,prompt_ids=[1,2],assistant_ids=[idx+5],n_new_tokens=8,parsed=parse_final(text,item),truncated=False,looped=False)


def judged(row,value,stance='ORIG',unjudgeable=False):
    return {**row,'assistant_ids':[3,4],'n_new_tokens':2,'truncated':False,'looped':False,
            'judge':dict(final_value=value,stance=stance,explicit='EXPLICIT',unjudgeable=unjudgeable)}


class Tests(unittest.TestCase):
    def test_exact_templates_and_frozen_sha(self):
        for value,sha in [(SR3,'262ab19955c7f51ec72f2d7f93850ad364467c130ef424799d72892ed922ba3c'),
                          (L3,'b9a73a3ff053c53ff5d806d08ff2b7ac9d261a9aeb84ac3827b54d1d6bc3e0d8'),
                          (MODE_PROMPT,'fc07b957bddf5d8251fdcab4d42d937ce6dcc53b73f8fa770dd11d718cd3e2e7')]:
            self.assertEqual(hashlib.sha256(value.encode()).hexdigest(),sha)
        self.assertEqual(third('SR',R,'Translator'),SR3.format(ROLE=ROLES['R'],D='Translator'))
        self.assertEqual(third('L',R,'Translator'),L3)
        reg=preregistration([R],'a'*40);sha=reg['frozen_sha256'];reg['calibration']={'admitted_ids':['R-001']}
        self.assertEqual(digest(reg['frozen']),sha)
        reg['frozen']['templates']['L3']+=' ';self.assertNotEqual(digest(reg['frozen']),sha)

    def test_shared_history_L_no_fourth(self):
        bank={'R-001':R};main=FakeMain();ss=make_seconds(main,[first(R,i,'Author') for i in range(8)],bank)
        self.assertEqual(len(ss),6)
        second=judged(ss[0],'Author');tasks=make_branches(main,[second],bank)
        self.assertEqual(len(tasks),26)
        self.assertEqual(len({tuple(r['shared_second_prompt_ids']) for r in tasks}),1)
        self.assertEqual(len({tuple(r['shared_second_assistant_ids']) for r in tasks}),1)
        self.assertEqual({r['shared_second_identity'] for r in tasks},{identity(second)})
        thirds=[judged(r,'Author') for r in tasks]
        fourths=make_fourths(main,thirds,bank)
        self.assertEqual(len(fourths),22);self.assertFalse(any(r['arm']=='L' for r in fourths))

    def test_F_actual_wrong_value_and_second_gate(self):
        bank={'F-001':F};main=FakeMain();rows=[first(F,i,'Other Person') for i in range(6)]+[first(F,6,'Translator')]
        seconds=make_seconds(main,rows,bank);self.assertEqual(len(seconds),4)
        self.assertEqual(seconds[0]['original'],'other person');self.assertEqual(seconds[0]['original_raw'],'Other Person')
        self.assertEqual(raw_final_value('Reason\n**Final answer: Other Person.**'),'Other Person')
        cases=[judged(seconds[0],'other person'),judged(seconds[1],'Translator','USER'),judged(seconds[2],'other person',unjudgeable=True)]
        tasks=make_branches(main,cases,bank);self.assertEqual(len(tasks),8)
        self.assertEqual({r['arm'] for r in tasks},{'D','N'})
        self.assertTrue(all(r['candidate']=='Translator' and r['original']=='other person' and r['original_raw']=='Other Person' for r in tasks))

    def test_missing_e3_not_filled_and_other_not_recovery(self):
        base=dict(conflict_id='R-001',pool='R',idx=0,path='correct',arm='S',rep=0,phase='formal',candidate='Translator',truncated=False,looped=False)
        t3={**base,'t':3,'judge':{'unjudgeable':True}}
        t4={**base,'t':4,'parsed':dict(value='Someone Else',kind='other')}
        row=branch_outcomes([t3],[t4],{'R-001':R})[0]
        self.assertIsNone(row['e3']);self.assertEqual(row['e4'],0);self.assertEqual(row['recovered'],0);self.assertEqual(row['other4'],1)
        self.assertIsNone(parse_mode('nonsense'));self.assertEqual(parse_mode('{"mode":"MIXED"}'),'MIXED')
        xs=[joint_event(r,'RETAINED') for r in [dict(e3=1,mode='RETAINED'),dict(e3=1,mode=None)]]
        rate=planned_rate(xs);self.assertEqual(rate['value'],.5);self.assertEqual(rate['observed_rate'],1);self.assertEqual(rate['bounds'],[.5,1])

    def test_six_history_missing_bound_and_conservative_go(self):
        uv=[([0,.5],[.25,.75]),([.25,1],[0,.5]),([.5,.5],[.75,1]),([0,.25],[0,1]),([.1,.4],[.2,.6]),([0,1],[0,1])]
        points=list(product(*[x for pair in uv for x in pair]));self.assertEqual(len(points),4096)
        expected=[covariance(list(p[::2]),list(p[1::2])) for p in points]
        self.assertEqual(covariance_bounds(uv),[min(expected),max(expected)])
        p=prefix_stats({'S':[1,None,0,None,1,0,None,1],'SR':[0]*8,'N':[0,None,0,1],'C':[0,1]})
        self.assertEqual(p['u_bounds'],[.5,.75]);self.assertEqual(p['v_bounds'],[.25,.75])
        i=instance_stats([p,p]);self.assertEqual(i['S-N']['conservative'],3/8-2/4)
        stats=group_stats([i],42,30);self.assertEqual(stats['bootstrap95']['S-N_conservative'],[-.125,-.125])

    def test_vw_null_no_history_heterogeneity(self):
        rng=random.Random(20261029);values=[]
        for _ in range(10000):
            u=[sum(rng.random()<.5 for _ in range(4))/4 for h in range(6)]
            v=[sum(rng.random()<.5 for _ in range(4))/4 for h in range(6)]
            values.append(covariance(u,v))
        self.assertLess(abs(sum(values)/len(values)),.002)
        self.assertEqual(covariance([.2]*6,[.8]*6),0)

    def test_all_F_first_correct_empty_branches_summarize(self):
        items=[{**R,'conflict_id':f'R-{j:03d}'} for j in range(1,4)]+[F]
        bank={i['conflict_id']:i for i in items};rows=[first(i,j,i['gold']) for i in items for j in range(16)]
        seconds=[judged(r,'Author',unjudgeable=True) for r in make_seconds(FakeMain(),rows,bank)]
        self.assertEqual(len(seconds),18);self.assertFalse(any(r['pool']=='F' for r in seconds))
        self.assertEqual(make_branches(FakeMain(),seconds,bank),[])
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            out=Path(tmp);save(out/'factdiag2_conflicts.json',items)
            save(out/'factdiag2_prereg.json',dict(calibration=dict(admitted_ids=[i['conflict_id'] for i in items if i['pool']=='R'],F_ids=['F-001'])))
            save(out/'calibration_t1.json',rows);save(out/'pilot_t2.json',seconds)
            for name in ('pilot_t3','pilot_t4','remaining_t2','remaining_t3','remaining_t4'):
                self.assertEqual(run_tasks(None,[],out/(name+'.json')),[])
                self.assertEqual(load(out/(name+'.json')),[])
            save(out/'budget.json',dict(over_budget=False,projected_total=512,limitation='测试'))
            save(out/'blind_matching.json',[]);save(out/'annotations.json',[]);validate(out,out/'annotations.json')
            result=summarize(out,complete=True);self.assertEqual(result['status'],'完整批已完成')
            result=load(out/'factdiag2_summary.json')
            self.assertEqual(result['Q4']['F']['branchable_histories'],0)
            self.assertIsNone(result['Q4']['F']['arms']['D']['a3']['value'])
            self.assertEqual(result['go']['status'],'不可算')


if __name__=='__main__':unittest.main()
