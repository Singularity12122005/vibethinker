import copy
import unittest
from collections import Counter
from .mention_holdout import choose,column_extraction


class MentionHoldoutTests(unittest.TestCase):
    def test_forty_balanced_excludes_old_without_labels(self):
        frame=[]
        cells={'baseline':[('X','S'),('F_w','S'),('X','C')],'Q2':[('X','A0'),('F_w','A1'),('X','A1'),('F_w','A0')]}
        for i in range(10):
            for phase,cs in cells.items():
                for kind,arm in cs:
                    for j in range(4):
                        frame.append(dict(work_id=str(i),phase=phase,candidate_type=kind,arm=arm,response_id=f'{i}|{phase}|{kind}|{arm}|{j}'))
        excluded={r['response_id'] for r in frame if r['response_id'].endswith('|0')}
        rows=choose(frame,excluded)
        self.assertEqual(len(rows),40)
        self.assertEqual(Counter(r['phase'] for r in rows),{'baseline':20,'Q2':20})
        self.assertEqual(Counter(r['work_id'] for r in rows),{str(i):4 for i in range(10)})
        self.assertFalse({r['response_id'] for r in rows}&excluded)
        self.assertEqual(rows,choose(list(reversed(frame)),excluded))

    def test_original_not_mutated_and_nonselected_reused(self):
        q={'id':'a','response':'Storer is named.','person':{'name':'Edward Storer','aliases':['Storer']}}
        r={'completion':'returned','extraction':{'mention':'ABSENT','claims':[],'extraction_flags':[],'parse_status':'OK'}}
        before=copy.deepcopy(r)
        cols=column_extraction(q,r,{},set())
        self.assertEqual(r,before)
        self.assertEqual(cols['original'],cols['reprompt'])
        self.assertIn('MENTION_MISMATCH',cols['original']['extraction_flags'])

    def test_selected_absent_stays_unknown_even_no_literal_match(self):
        q={'id':'a','response':'He is credited.','person':{'name':'Samuel Butler','aliases':['Butler']}}
        r={'completion':'returned','extraction':{'mention':'ABSENT','claims':[],'extraction_flags':[],'parse_status':'OK'}}
        cols=column_extraction(q,r,{'a':{'attempts':[r]}},{'a'})
        self.assertIn('MENTION_MISMATCH',cols['reprompt']['extraction_flags'])


if __name__=='__main__':unittest.main()
