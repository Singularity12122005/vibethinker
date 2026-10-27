import unittest
from formal_results import measure, paired


class FrozenTables(unittest.TestCase):
    def row(self,w,h,a,v,c=None):
        return dict(work_id=w,cluster_id=c or w,history_id=h,arm=a,candidate_type='d',event=v)

    def test_project_and_history_weight_differ(self):
        rows=[self.row('a','a1','S',1),self.row('a','a2','S',1),self.row('b','b1','S',0)]
        result=measure(rows,'event')
        self.assertEqual(result['project_equal']['point'],.5)
        self.assertAlmostEqual(result['history_equal']['point'],2/3)

    def test_missing_conservative_difference(self):
        rows=[self.row('a','h','S',1),self.row('a','h','S',None),
              self.row('a','h','C',0),self.row('a','h','C',None)]
        result=paired(rows,'S','C','event')
        self.assertEqual(result['project_equal']['point'],1)
        self.assertEqual(result['project_equal']['bounds'],[0,1])

    def test_movie_directions_one_cluster_not_two(self):
        rows=[self.row('a','a','S',1,'pair'),self.row('b','b','S',0,'pair')]
        result=measure(rows,'event')
        self.assertEqual(result['projects'],2)
        self.assertEqual(result['clusters'],1)
        self.assertIsNone(result['project_equal']['ci95'])

    def test_zero_event_no_degenerate_interval(self):
        result=measure([self.row('a','a','S',0),self.row('b','b','S',0)],'event')
        self.assertIsNone(result['project_equal']['ci95'])
        self.assertEqual(result['project_equal']['bounds'],[0,0])


if __name__=='__main__':unittest.main()
