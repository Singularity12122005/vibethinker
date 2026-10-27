import unittest
from collections import Counter
from adaptation_materials import build as adaptations
from version_materials import build as versions
from screen import parse_final
from legacy import previous


class Tests(unittest.TestCase):
    def test_adaptation_fixed_items_and_negative_limit(self):
        items=adaptations()
        self.assertEqual(len(items),24)
        counts=Counter(i['candidates'][2]['name'] for i in items)
        self.assertTrue(all(n==2 for n in counts.values()))
        for i in items:
            self.assertEqual({c['type'] for c in i['candidates']},{'D','A','N'})
            self.assertLess(i['negative_check']['death_year'],i['novel_year'])
            self.assertEqual(i['candidates'][2]['proposition'],None)

    def test_version_fixed_identities_across_directions(self):
        items=versions()
        self.assertEqual(len(items),50)
        for i,j in zip(items[::2],items[1::2]):
            self.assertEqual(i['fixed_alpha'],j['fixed_alpha'])
            self.assertEqual(i['fixed_beta'],j['fixed_beta'])
            self.assertEqual(i['gold'],j['candidates'][0]['name'])
            self.assertEqual(j['gold'],i['candidates'][0]['name'])
            self.assertEqual(i['pair_id'],j['pair_id'])

    def test_joint_director_identity_requires_both(self):
        item=next(i for i in versions() if i['title']=='West Side Story' and i['year']==1961)
        old=previous().p3.old
        self.assertEqual(parse_final('Final answer: Wise and Robbins',item,old)['kind'],'gold')
        self.assertNotEqual(parse_final('Final answer: Robert Wise',item,old)['kind'],'gold')


if __name__=='__main__':unittest.main()
