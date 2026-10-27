import unittest
from readouts import pair,prompts,sample_orders,definitions,sample_seed


class Tests(unittest.TestCase):
    def test_order_does_not_reverse_identities(self):
        d=pair('Who directed the 1972 film Solaris?','Andrei Tarkovsky','Steven Soderbergh',samples=4)
        self.assertEqual(sample_orders(d).count(0),2)
        self.assertEqual(sample_orders(d).count(1),2)
        self.assertIn('Andrei Tarkovsky; Steven Soderbergh',prompts(d)[0])
        self.assertIn('Steven Soderbergh; Andrei Tarkovsky',prompts(d)[1])
        self.assertEqual(d['left'],'Andrei Tarkovsky')

    def test_current_answer_policy_and_gold_not_conflated(self):
        i=dict(item_id='F',work_id='W',structure='G1',subject='a specified edition',
               question_en='Who translated it?',gold='True Translator',
               candidates=[dict(type='T',name='True Translator')],
               policy_pairs=[dict(x='Wrong Translator',d='True Translator',reference='h1')])
        c=definitions([i])
        self.assertNotIn('delta_gold',[r['readout'] for r in c['references']])
        r=next(r for r in c['references'] if r['readout']=='delta_pol')
        self.assertEqual(c['definitions'][r['key']]['left'],'Wrong Translator')
        self.assertEqual(c['definitions'][r['key']]['right'],'True Translator')

    def test_same_relation_prompt_is_sampled_once(self):
        i=dict(item_id='a',work_id='w',structure='G2b',subject='a film',question_en='q',
               wording_question='q2',fixed_alpha='a',fixed_beta='b',gold='a',
               candidates=[dict(type='d',name='b')])
        c=definitions([i,dict(i,item_id='b')])
        self.assertEqual(sum(d['kind']=='relation' for d in c['definitions'].values()),1)
        self.assertNotEqual(sample_seed('x',0),sample_seed('x',1))

    def test_computable_control_only_planned_easy_items(self):
        from readout_materials import computable
        items=computable()
        self.assertEqual(len(items),96)
        self.assertEqual(sum(c['type']=='d_control' for i in items for c in i['candidates']),48)
        self.assertEqual(sum(d.get('samples',0) for d in definitions(items)['definitions'].values()),576)


if __name__=='__main__':unittest.main()
