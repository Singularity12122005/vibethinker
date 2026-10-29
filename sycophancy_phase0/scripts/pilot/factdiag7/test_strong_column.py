import unittest
from .strong_column import safety_stop,pilot_decision,alternate


class StrongBudgetTests(unittest.TestCase):
    def test_included_allowance_cannot_be_zero_cost_release(self):
        before={'credits':{'balance':'16230'},'primary':{'usedPercent':78}}
        after={'credits':{'balance':'16230'},'primary':{'usedPercent':82}}
        usage=[dict(input_tokens=100,cached_input_tokens=95,output_tokens=10)]*200
        self.assertFalse(pilot_decision(before,after,usage)['allow'])
        self.assertIsNone(pilot_decision(before,after,usage)['projection_first_layer'])
    def test_release_requires_both_cost_and_cache(self):
        before={'credits':{'balance':'16230'},'primary':{'usedPercent':100}}
        after={'credits':{'balance':'16030'},'primary':{'usedPercent':100}}
        usage=[dict(input_tokens=100,cached_input_tokens=85,output_tokens=10) for _ in range(200)]
        self.assertTrue(pilot_decision(before,after,usage)['allow'])
        for row in usage:row['cached_input_tokens']=79
        self.assertFalse(pilot_decision(before,after,usage)['allow'])
    def test_hard_stops(self):
        self.assertIsNotNone(safety_stop(20000,10000,[],[]))
        self.assertIsNotNone(safety_stop(16230,6499,[],[]))
        self.assertIsNone(safety_stop(16230,16000,[.7]*199,[]))
        self.assertIsNotNone(safety_stop(16230,16000,[.7]*200,[]))
        self.assertIsNotNone(safety_stop(16230,16000,[],[201],100))
    def test_q2_order(self):
        rows=[dict(id=str(i),arm='S+A1' if i%2 else 'S+A0') for i in range(8)]
        self.assertEqual([q['arm'] for q in alternate(rows)],['S+A1','S+A0']*4)


if __name__=='__main__':unittest.main()
