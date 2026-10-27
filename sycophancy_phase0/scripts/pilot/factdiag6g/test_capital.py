import unittest
from capital_materials import build,PRESELECTED
from readouts import definitions


class CapitalTests(unittest.TestCase):
    def test_all_preselected_retained_or_explained(self):
        items,excluded=build()
        self.assertEqual({x['country'] for x in items+excluded},set(PRESELECTED))
        self.assertEqual(len(items)+len(excluded),len(PRESELECTED))

    def test_colonial_is_not_main(self):
        item=next(i for i in build()[0] if i['country']=='Belize')
        self.assertEqual({c['type'] for c in item['candidates']},{'L','N'})
        self.assertFalse(item['side_candidates'][0]['main_effect'])
        self.assertEqual(next(i for i in build()[0] if i['country']=='Brazil')['former_capital']['start'],1822)

    def test_largest_equals_capital_keeps_other_conditions(self):
        item=next(i for i in build()[0] if i['country']=='Germany')
        self.assertTrue(item['no_wrong_largest_candidate'])
        self.assertFalse(item['trial_eligible_material'])
        self.assertEqual({c['type'] for c in item['candidates']},{'P','N'})

    def test_overlapping_true_roles_and_readout_reuse(self):
        item=next(i for i in build()[0] if i['country']=='Pakistan')
        candidates=[c for c in item['candidates'] if c['name']=='Karachi']
        self.assertEqual(len(candidates),2)
        self.assertTrue(all(set(c['true_roles'])=={'LARGEST_CITY','FORMER_CAPITAL'} for c in candidates))
        d=definitions([item])
        relations=[v for v in d['definitions'].values() if v['kind']=='relation' and v['D']=='Karachi']
        self.assertEqual(len(relations),1)


if __name__=='__main__':unittest.main()
