"""阶段二输入、已登记身份、联合预算的处理器检查。"""
import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from stage2_plan import tasks,identity,seed_for
from stage2_budget import used_tokens,check_next_batch


class Stage2Tests(unittest.TestCase):
    def test_no_repeated_seeds_and_original_history(self):
        class Engine:
            def continue_from(self,row,text):return row['prompt_ids']+row['assistant_ids']+[len(text)]
            def first(self,text):return [len(text)]
        plan={'items':[{'work_id':'R-001','item_id':'R-001-R','gold':'Author','title':'Work','ebook':'1',
                        'people':[{'type':'X','name':'Other Name'}]}],
              'histories':[{'work_id':'R-001','history_id':'R-S|R-001|0','idx':0}],
              'conditions':[{'work_id':'R-001','history_id':'R-S|R-001|0','candidate_type':'X','arm':a,'n':4}
                            for a in ['S+A1','S+A0']],
              'templates':{'S_D':'claim {D}','A1':'prefix 1 ','A0':'prefix 0 '},'counts':{'Q2':8}}
        source={'R-S|R-001|0':{'prompt_ids':[1,2],'assistant_ids':[3,4],'n_new_tokens':2}}
        q=tasks(Engine(),plan,source,'Q2')
        self.assertEqual(len({identity(r) for r in q}),8)
        self.assertEqual(len({seed_for(r) for r in q}),8)
        self.assertTrue(all(r['prompt_ids'][:4]==[1,2,3,4] for r in q))
        self.assertEqual({r['user_text'] for r in q},{'claim Other Name'})
        self.assertEqual({r['forced_prefix'] for r in q},{'prefix 1 ','prefix 0 '})
    def test_shared_budget_excludes_old_and_judge_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);q=p/'factdiag7_20261112';q.mkdir();f=p/'factdiag5_20261112';f.mkdir()
            (q/'stage2_Q2_generations.json').write_text(json.dumps([{'n_new_tokens':100}]))
            (q/'stage2_belief_generations.json').write_text(json.dumps([{'n_new_tokens':20}]))
            (f/'core_generations.json').write_text(json.dumps([{'n_new_tokens':200}]))
            (q/'stage2_baseline_extractions.json').write_text(json.dumps({'old':{'n_new_tokens':99999}}))
            self.assertEqual(used_tokens(p)['total'],320)
            self.assertEqual(check_next_batch(p,16)['total'],320)
            (f/'core_generations.json').write_text(json.dumps([{'n_new_tokens':1490000}]))
            with self.assertRaises(RuntimeError):check_next_batch(p,16)


if __name__=='__main__':unittest.main()
