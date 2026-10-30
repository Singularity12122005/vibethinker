"""仅验证指令九新数学与保留分母规则，不调用真实产物。"""
import math
import unittest

from .t1_endline import fit, weights, pairs, empirical_interval, decision, bootstrap


def row(work, k0, k1, n0=1, n1=1):
    return dict(work_id=work, history_id=work, n0=n0, k0=k0, n1=n1, k1=k1)


class ConditionalEndlineTests(unittest.TestCase):
    def test_discordant_pairs_closed_form(self):
        rows = [row('a', 1, 0)]*3 + [row('b', 0, 1)]
        result = fit(rows)
        self.assertAlmostEqual(result['estimate'], math.log(3), places=8)
        self.assertLess(result['profile95'][0], result['estimate'])
        self.assertGreater(result['profile95'][1], result['estimate'])

    def test_work_equal_weights(self):
        rows = [row('a', 1, 0)]*3 + [row('b', 0, 1)]
        self.assertAlmostEqual(sum(weights(rows, 'work_equal')), 4)
        self.assertAlmostEqual(fit(rows, 'work_equal')['estimate'], 0, places=8)

    def test_positive_separation_single_sided(self):
        result = fit([row('a', 1, 0)]*4)
        expected = -math.log(math.exp(2.7055435/8)-1)
        self.assertEqual(result['estimate'], math.inf)
        self.assertAlmostEqual(result['profile95'][0], expected, places=8)
        self.assertEqual(result['profile95'][1], math.inf)

    def test_negative_separation_symmetry(self):
        plus = fit([row('a', 1, 0)]*4)
        minus = fit([row('a', 0, 1)]*4)
        self.assertEqual(minus['estimate'], -math.inf)
        self.assertAlmostEqual(minus['profile95'][1], -plus['profile95'][0])

    def test_no_information_and_infinite_quantiles(self):
        self.assertIsNone(fit([row('a', 1, 1)])['estimate'])
        self.assertEqual(empirical_interval([math.inf]*2000), [math.inf, math.inf])
        self.assertIsNone(empirical_interval([None]*10))
        self.assertIn('不能据此判决', decision([0, 1], [math.inf, math.inf], [0, 1])['H1'])

    def test_reserved_stays_in_main_denominator(self):
        records = [dict(cohort='X', work_id='a', history_id='h', arm=a, reserved=r, success=s)
                   for a, r, s in [('S', False, 1), ('S', True, 0), ('S+A1', False, 0), ('S+A1', True, 0)]]
        main = pairs(records, 'X', 'S', 'S+A1')[0]
        sensitivity = pairs(records, 'X', 'S', 'S+A1', True)[0]
        self.assertEqual((main['n0'], main['n1'], main['k0']), (2, 2, 1))
        self.assertEqual((sensitivity['n0'], sensitivity['n1'], sensitivity['k0']), (1, 1, 1))

    def test_symmetric_four_continuations(self):
        result = fit([row('a', 1, 3, 4, 4), row('b', 3, 1, 4, 4)])
        self.assertAlmostEqual(result['estimate'], 0, places=8)
        self.assertAlmostEqual(result['profile95'][0], -result['profile95'][1], places=8)

    def test_bootstrap_tracks_unidentified(self):
        result = bootstrap([row('a', 1, 1), row('b', 1, 1)], 'work_equal', 'work', 12)
        self.assertEqual(result['unidentified'], 12)
        self.assertEqual(result['defined'], 0)
        self.assertIsNone(result['interval95'])


if __name__ == '__main__':
    unittest.main()
