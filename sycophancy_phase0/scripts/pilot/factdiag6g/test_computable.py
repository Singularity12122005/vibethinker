import unittest
from collections import Counter
from fractions import Fraction
from computable import build,execute_function


class ComputableTests(unittest.TestCase):
    def test_frozen_scale_and_answers(self):
        items=build()
        self.assertEqual(len(items),96)
        self.assertEqual(Counter((m['family'],m['level']) for m in items),
                         {('mean',9):24,('mean',15):24,('code','simple'):24,('code','nested'):24})
        for m in items:
            self.assertEqual(len({m[k] for k in ('gold','d','d_control','x')}),4)
            if m['family']=='mean':
                ns=m['spec']['numbers'];gold=Fraction(sum(ns),len(ns))
                self.assertEqual(int(m['gold']),gold)
                self.assertNotIn(int(m['gold']),ns)
                self.assertEqual(int(m['d']),sorted(ns)[len(ns)//2])
                self.assertTrue(2<=abs(int(m['x'])-gold)<=7)
                self.assertNotIn(int(m['x']),ns)
            else:
                self.assertEqual(execute_function(m['code'],m['spec']['argument']),
                                 (int(m['gold']),int(m['d'])))
                s=m['spec'];v=s['argument']*s['multiplier'];seen={v,s['argument']}
                if s['nested']:
                    seen.update(range(s['iterations']))
                    seen.add(s['return_offset'])
                    for j in range(s['iterations']):
                        v+=s['addend'] if j%2==0 else -s['subtrahend']
                        seen.add(v)
                else:
                    seen.add(v+s['addend'])
                self.assertNotIn(int(m['x']),seen)

    def test_reject_external_operations(self):
        with self.assertRaises(ValueError):
            execute_function('def f(n):\n    import os\n    return n',1)


if __name__=='__main__':unittest.main()
