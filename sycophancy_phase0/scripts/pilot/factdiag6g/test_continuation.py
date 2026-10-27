import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core import save
from continue_formal import projection,STAGES,run


class Tests(unittest.TestCase):
    def test_projection_counts_only_remaining_and_preserves_all_cells(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            out=Path(tmp);sample=dict(n_new_tokens=100,truncated=False,looped=False)
            save(out/'formal_g1_non_a0_generations.json',[sample]*2)
            save(out/'formal_g1_a0_generations.json',[sample]*2)
            plan={'counts':{s:10 for s in STAGES}}
            reg={'frozen':{'budget':{'mean_length_assumptions':{s:200 for s in STAGES}}}}
            with patch('continue_formal.token_total',return_value=1000):
                result=projection(out,reg,plan)
            self.assertEqual(result['remaining_requests']['g1_a0'],8)
            self.assertEqual(result['projected_total'],1000+800+4*2000)
            self.assertEqual(plan['counts'],{s:10 for s in STAGES})

    def test_warning_and_pause_are_distinct(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            out=Path(tmp);save(out/'formal_g1_non_a0_generations.json',[dict(n_new_tokens=100)])
            plan={'counts':{s:0 for s in STAGES}}
            reg={'frozen':{'budget':{'mean_length_assumptions':{s:200 for s in STAGES}}}}
            with patch('continue_formal.token_total',return_value=1200000):
                a=projection(out,reg,plan)
            with patch('continue_formal.token_total',return_value=1500000):
                b=projection(out,reg,plan)
            self.assertTrue(a['warning']);self.assertFalse(a['pause']);self.assertTrue(b['pause'])

    def test_no_generation_without_matching_committed_prediction(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            out=Path(tmp)
            save(out/'a0_prediction_frozen.json',dict(prediction_commit='a'*40,models={'B':{}}))
            with patch('continue_formal.validate_materials',return_value=({}, {}, {})),patch('continue_formal.subprocess.run') as process:
                with self.assertRaisesRegex(RuntimeError,'A0预测未单独冻结'):
                    run(out,out,'c'*40,'b'*40)
            process.assert_not_called()


if __name__=='__main__':unittest.main()
