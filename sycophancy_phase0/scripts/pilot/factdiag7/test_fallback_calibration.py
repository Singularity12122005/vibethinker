import unittest
from collections import Counter
from .fallback_calibration import choose
from .mention_followup_checks import normalized_quote_check,normalized_quote_column


class FallbackChecks(unittest.TestCase):
    def frame(self):
        return [dict(work_id=f'R-{w}',idx=h,arm=a,candidate_type=c,response_id=f'{w}|{h}|{a}|{c}|{r}')
            for w in range(10) for h in range(6) for a in ('S','S+A0','S+A1') for c in ('X','F_w') for r in range(4)]

    def test_work_history_arm_sample_and_determinism(self):
        rows=choose(self.frame(),'X',3,20261028)
        self.assertEqual(len(rows),90)
        self.assertEqual(len({r['response_id'] for r in rows}),90)
        self.assertEqual(Counter(r['arm'] for r in rows),{'S':30,'S+A0':30,'S+A1':30})
        self.assertEqual(Counter(r['work_id'] for r in rows),{f'R-{w}':9 for w in range(10)})
        self.assertEqual(rows,choose(list(reversed(self.frame())),'X',3,20261028))
        self.assertEqual(len(choose(self.frame(),'F_w',1,20261029)),30)

    def test_missing_arm_not_substituted(self):
        with self.assertRaises(ValueError):choose([r for r in self.frame() if r['arm']!='S+A0'],'X',3,0)

    def test_normalization_has_no_splicing_or_empty_match(self):
        self.assertTrue(normalized_quote_check({'quote':'NAME—“Translator”'},'**Name** - "translator"')['substring'] is False)
        self.assertTrue(normalized_quote_check({'quote':'NAME—“Translator”'},'**Name**—“translator”')['eligible'])
        self.assertFalse(normalized_quote_check({'quote':'A ... B'},'A intervening text B')['substring'])
        self.assertFalse(normalized_quote_check({'quote':''},'Anything')['substring'])

    def test_secondary_does_not_mutate_or_clear_other_flags(self):
        e={'claims':[{'quote':'A translator','flags':['QUOTE_MISSING','CONFLICTING']}]}
        new=normalized_quote_column(e,'A **translator**')
        self.assertEqual(e['claims'][0]['flags'],['QUOTE_MISSING','CONFLICTING'])
        self.assertEqual(new['claims'][0]['flags'],['CONFLICTING'])
        c={'quote':' '.join(['word']*31)}
        self.assertTrue(normalized_quote_check(c,c['quote'])['substring'])
        self.assertFalse(normalized_quote_check(c,c['quote'])['eligible'])


if __name__=='__main__':unittest.main()
