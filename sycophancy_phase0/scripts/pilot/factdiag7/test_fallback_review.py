import unittest
from .fallback_review import agreement,human_bound,selected_human_rows


class HumanCalibrationTests(unittest.TestCase):
    def test_unknown_does_not_inflate_gate_or_shrink_denominator(self):
        pairs=[([1,1],[1,1])]*7+[([0,1],[0,1])]*2+[([0,0],[0,0])]
        r=agreement(pairs)
        self.assertEqual(r['planned'],10)
        self.assertEqual(r['conservative_agreement'],.8)
        self.assertEqual(r['lower_marker_agreement'],1)
        self.assertEqual(r['determined_agreement'],1)
        self.assertTrue(r['calibrated'])
        failed=agreement(pairs[:-1]+[(None,[0,0])])
        self.assertEqual(failed['conservative_agreement'],.7)
        self.assertFalse(failed['calibrated'])

    def test_null_is_unknown_and_text_is_never_guessed(self):
        self.assertEqual(human_bound(None),[0,1])
        self.assertEqual(human_bound(0),[0,0])
        for x in ('0','unknown',[1,0],.5):
            with self.assertRaises(ValueError):human_bound(x)

    def test_priority60_keeps_unfinished_a0_without_treating_as_labels(self):
        keys=[];rows=[]
        for i in range(30):
            for arm in ('S','S+A0','S+A1'):
                k=dict(human_id=str(len(keys)),blind_id=str(len(keys)),work_id=str(i//3),idx=i,arm=arm,cohort='X_main')
                keys.append(k)
                rows.append(dict(human_id=k['human_id'],blind_id=k['blind_id'],work_id=k['work_id'],history_index=i,arm=arm,
                    human_review_complete=arm!='S+A0',W_false=None))
        document=dict(cohort='X_main',records=rows)
        self.assertEqual(len(selected_human_rows(keys,document,'X_main',True)),60)
        with self.assertRaises(ValueError):selected_human_rows(keys,document,'X_main')
        rows[0]['human_review_complete']=False
        with self.assertRaises(ValueError):selected_human_rows(keys,document,'X_main',True)


if __name__=='__main__':unittest.main()
