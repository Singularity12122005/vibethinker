import unittest
from collections import Counter
from .intervention8 import select,CELLS
from .batch5_strong import stop_reason,parse_draft

class Intervention8Test(unittest.TestCase):
    def frame(self):
        frame=[];control=[]
        for w in range(10):
            for h in range(6):
                for arm in ('none','A1'):
                    for c in CELLS:
                        for rep in range(2):frame.append(dict(work_id=str(w),idx=h,unit='R-S',cell=c,arm=arm,response_id=f'{w}-{h}-{arm}-{c}-{rep}'))
                    control.append(dict(work_id=str(w),idx=h,unit='R-S',cell='no_evidence',arm=arm,response_id=f'n-{w}-{h}-{arm}'))
            for unit in ('R-S','F-D','S_T'):frame.append(dict(work_id=str(w),idx=0,unit=unit,cell='5.5',arm='none',response_id=f'v-{w}-{unit}'))
        return frame,control
    def test_balanced_paired_sampling(self):
        f,c=self.frame();rows,hs,skip,b=select(f,c)
        self.assertEqual(Counter(r['cohort'] for r in rows),{'evidence':80,'no_evidence':20,'status':10})
        self.assertEqual(len(b),20);self.assertFalse(skip)
        for w in range(10):
            hh=[r for r in hs if r['work_id']==str(w)];self.assertEqual(len({r['idx'] for r in hh}),2);self.assertEqual({r['arm'] for r in hh},{'none','A1'})
        for h in hs:
            rr=[r for r in rows if r['cohort']!='status' and all(r[k]==h[k] for k in ('work_id','idx','arm'))]
            self.assertEqual(len(rr),5)
    def test_labels_do_not_change_selection(self):
        f,c=self.frame();expected=select(f,c)
        for r in f+c:r.update(judge={'wrong':True},flags=['MISS'],W_false=1)
        actual=select(f,c)
        self.assertEqual([r['response_id'] for r in expected[0]],[r['response_id'] for r in actual[0]])
    def test_missing_history_excluded_before_selection(self):
        f,c=self.frame();f=[r for r in f if not(r['work_id']=='0' and r['idx']==0 and r['cell']=='M-right')]
        rows,hs,skip,b=select(f,c)
        self.assertEqual(len(skip),1);self.assertFalse(any(r['work_id']=='0' and r['idx']==0 for r in hs))
    def test_budget_and_rolling_output(self):
        self.assertIsNotNone(stop_reason('16500','6500',[]))
        self.assertIsNotNone(stop_reason('7000','6499',[]))
        self.assertIsNone(stop_reason('16000','15000',[9999]*199))
        self.assertIsNone(stop_reason('16000','15000',[9999]*200+[100]*200))
        self.assertIsNotNone(stop_reason('16000','15000',[2633]*200))
    def test_draft_cannot_mark_human_complete(self):
        import json
        with self.assertRaises(ValueError):parse_draft(json.dumps({'human_id':'x','human_review_complete':True}),{'human_id':'x'})

if __name__=='__main__':unittest.main()
