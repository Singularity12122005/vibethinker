import unittest
from unittest.mock import patch

from .mention_reprompt import insert_note,next_attempt,serial
from .mention_diagnostic import NOTE,MARKER


class MentionRepromptTests(unittest.TestCase):
    def test_only_note_changes_bytes(self):
        original='RULES\nCANDIDATE\n'+MARKER+'\n**Butler** wrote it.\n'
        result=insert_note(original,'Butler')
        self.assertEqual(result.replace(NOTE.replace('{NAME_FORM}','Butler')+'\n','',1),original)
        with self.assertRaises(ValueError):insert_note(original,None)

    def test_retry_only_returned_unparseable_once(self):
        def rec(status,completion='returned',n=1):
            return {'attempts':[{'completion':completion,'extraction':{'parse_status':status}}]*n}
        self.assertEqual(next_attempt(None),1)
        self.assertEqual(next_attempt(rec('UNPARSEABLE')),2)
        self.assertIsNone(next_attempt(rec('OK')))
        self.assertIsNone(next_attempt(rec('UNPARSEABLE',n=2)))
        self.assertIsNone(next_attempt(rec('UNPARSEABLE','attempted_result_missing')))

    def test_batch_first_then_one_exception_no_best_selection(self):
        qs=[{'id':x,'input_sha256':x,'reprompt_sha256':x,'reprompt':x} for x in ('a','b')]
        saved={};calls=[];writes=[]
        def infer(prompts,limit):
            calls.append(list(prompts))
            return [{'parse_status':'UNPARSEABLE' if p=='a' else 'OK','raw':str(len(calls))} for p in prompts]
        def finish_stub(store,q,value):
            store[q['id']] |= {'completion':'returned','extraction':{'parse_status':value['parse_status']},'raw':value['raw']}
        with patch('scripts.pilot.factdiag7.mention_reprompt.finish',finish_stub):
            serial(qs,saved,{'batch':8,'max_new_tokens':2048},'c'*40,infer,lambda d:writes.append(len(d)))
        self.assertEqual(calls,[['a','b'],['a']])
        self.assertEqual(len(saved['a']['attempts']),2)
        self.assertEqual(saved['a']['selected_attempt'],2)
        self.assertEqual(saved['a']['attempts'][0]['raw'],'1')
        self.assertEqual(saved['a']['attempts'][1]['raw'],'2')
        self.assertEqual(len(saved['b']['attempts']),1)
        with patch('scripts.pilot.factdiag7.mention_reprompt.finish',finish_stub):
            serial(qs,saved,{'batch':8,'max_new_tokens':2048},'c'*40,infer,lambda d:None)
        self.assertEqual(len(calls),2)

    def test_nonselected_saved_id_stops_before_dispatch(self):
        with self.assertRaises(ValueError):
            serial([],{'unselected':{}},{'batch':8,'max_new_tokens':2048},'c'*40,
                   lambda *a:self.fail('不应调用模型'),lambda d:None)


if __name__=='__main__':unittest.main()
