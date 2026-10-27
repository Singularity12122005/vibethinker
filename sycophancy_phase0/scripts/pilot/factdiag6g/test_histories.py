import unittest
from histories import select_first,trial_selection


def row(idx,value,gold='Right',text=''):
    return dict(conflict_id='i',idx=idx,parsed=dict(value=value,kind='gold' if value==gold else 'other'),
                truncated=False,looped=False,assistant_text=text)


class Tests(unittest.TestCase):
    def item(self,structure='G2c'):
        return dict(item_id='i',work_id='i',structure=structure,gold='Right',gold_aliases=['Right'],
                    answer_format='entity',candidates=[dict(type='D' if structure=='G2c' else 'd',name='Jane Doe',aliases=['Doe'])])

    def test_adaptation_exposure_balanced_before_fill(self):
        rows=[row(i,'Right',text='Director Doe.' if i<4 else 'No mention.') for i in range(8)]
        chosen,_=select_first(dict(items=[self.item()]),rows)
        self.assertEqual([r['idx'] for r in chosen],[0,4])

    def test_stability_uses_all_eight_and_aliases(self):
        item=self.item('G2b')
        rows=[row(i,'Jane Doe' if i%2 else 'Doe') for i in range(7)]+[row(7,'Right')]
        chosen,_=select_first(dict(items=[item]),rows)
        self.assertEqual([(r['idx'],r['path']) for r in chosen],[(7,'correct'),(0,'natural_wrong')])
        rows[0]['truncated']=True
        chosen,_=select_first(dict(items=[item]),rows)
        self.assertEqual(len(chosen),1)

    def test_trial_does_not_require_second_correct_but_excludes_dx(self):
        item=self.item('G2b')
        h=dict(conflict_id='i',idx=0,path='correct',current_value='Other',truncated=False,looped=False)
        chosen,_=trial_selection([item],[h])
        self.assertEqual(len(chosen),1)
        h['current_value']='Doe'
        chosen,excluded=trial_selection([item],[h])
        self.assertFalse(chosen)
        self.assertEqual(excluded[0]['reason'],'d=x')

    def test_trial_no_wrong_largest_candidate_not_replaced(self):
        item=self.item('G2a');item['candidates']=[dict(type='N',name='City',aliases=[])]
        h=dict(conflict_id='i',idx=0,path='correct',current_value='Right',truncated=False,looped=False)
        self.assertFalse(trial_selection([item],[h])[0])


if __name__=='__main__':unittest.main()
