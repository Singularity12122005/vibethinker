import unittest
import json
import tempfile
import hashlib
import subprocess
from pathlib import Path
from unittest.mock import patch
from .strong_column import safety_stop,pilot_decision,alternate
from .strong_column import PLAN,OUTPUT,save_result
from .strong_codex import resume_state,infer


class StrongBudgetTests(unittest.TestCase):
    def test_included_allowance_cannot_be_zero_cost_release(self):
        before={'credits':{'balance':'16230'},'primary':{'usedPercent':78}}
        after={'credits':{'balance':'16230'},'primary':{'usedPercent':82}}
        usage=[dict(input_tokens=100,cached_input_tokens=95,output_tokens=10)]*200
        self.assertFalse(pilot_decision(before,after,usage)['allow'])
        self.assertIsNone(pilot_decision(before,after,usage)['projection_first_layer'])
    def test_release_requires_both_cost_and_cache(self):
        before={'credits':{'balance':'16230'},'primary':{'usedPercent':100}}
        after={'credits':{'balance':'16030'},'primary':{'usedPercent':100}}
        usage=[dict(input_tokens=100,cached_input_tokens=85,output_tokens=10) for _ in range(200)]
        self.assertTrue(pilot_decision(before,after,usage)['allow'])
        for row in usage:row['cached_input_tokens']=79
        self.assertFalse(pilot_decision(before,after,usage)['allow'])
    def test_hard_stops(self):
        self.assertIsNotNone(safety_stop(20000,10000,[],[]))
        self.assertIsNotNone(safety_stop(16230,6499,[],[]))
        self.assertIsNone(safety_stop(16230,16000,[.7]*199,[]))
        self.assertIsNotNone(safety_stop(16230,16000,[.7]*200,[]))
        self.assertIsNotNone(safety_stop(16230,16000,[],[201],100))
    def test_q2_order(self):
        rows=[dict(id=str(i),arm='S+A1' if i%2 else 'S+A0') for i in range(8)]
        self.assertEqual([q['arm'] for q in alternate(rows)],['S+A1','S+A0']*4)

    def test_resume_preserves_completed_usage_and_only_retries_missing66(self):
        ids=[str(i) for i in range(200)]
        limits={'credits':{'balance':'16230'},'primary':{'usedPercent':81}}
        rows=[dict(type='pilot_start',limits=limits)]
        for i in range(66):
            rows.extend([dict(type='dispatched',id=ids[i]),dict(type='result',id=ids[i],metadata=dict(
                attempts=1,completion='returned' if i<65 else 'attempted_result_missing',
                usage=dict(input_tokens=100,cached_input_tokens=20,output_tokens=50) if i<65 else None))])
        state=resume_state(rows,ids)
        self.assertEqual(state['ids'],ids[65:])
        self.assertEqual(len(state['usage']),65)
        self.assertEqual(state['limits'],limits)
        with self.assertRaises(ValueError):resume_state(rows+[dict(type='resume_start')],ids)
        rows[-1]['metadata']['completion']='returned'
        with self.assertRaises(ValueError):resume_state(rows,ids)

    def test_authorized_retry_keeps_original_failure_and_blocks_further_replacement(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'factdiag7_20261112';out.mkdir()
            q=dict(id='66',input_sha256='input',prompt_sha256='prompt')
            (out/PLAN).write_text(json.dumps(dict(entries=[q])))
            failed=dict(input_sha256='input',prompt_sha256='prompt',attempts=1,
                completion='attempted_result_missing',raw=None)
            (out/OUTPUT).write_text(json.dumps({'66':failed}))
            result=dict(failed,attempts=2,completion='returned',raw='result',retry_authorization='用户确认')
            with self.assertRaises(ValueError):save_result(temp,'66',result)
            save_result(temp,'66',result,retry_missing='66')
            stored=json.loads((out/OUTPUT).read_text())['66']
            self.assertEqual(stored['previous_attempts'],[failed])
            self.assertEqual(stored['raw'],'result')
            with self.assertRaises(ValueError):save_result(temp,'66',dict(result,raw='different'),retry_missing='66')

    def test_retry_cannot_replace_valid_label(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'factdiag7_20261112';out.mkdir()
            (out/PLAN).write_text(json.dumps(dict(entries=[dict(id='66',input_sha256='i',prompt_sha256='p')])))
            valid=dict(input_sha256='i',prompt_sha256='p',attempts=1,completion='returned',raw='existing')
            (out/OUTPUT).write_text(json.dumps({'66':valid}))
            with self.assertRaises(ValueError):
                save_result(temp,'66',dict(valid,attempts=2,raw='new',retry_authorization='用户确认'),retry_missing='66')
            self.assertEqual(json.loads((out/OUTPUT).read_text())['66'],valid)

    def test_failed_call_keeps_redacted_error_without_local_error_body(self):
        q=dict(prompt='fixed',prompt_sha256=hashlib.sha256(b'fixed').hexdigest(),input_sha256='i',response='text')
        proc=subprocess.CompletedProcess([],1,
            json.dumps(dict(type='turn.failed',error=dict(message='stream disconnected')))+'\n',
            'connection failed; Bearer secret-example')
        with patch('scripts.pilot.factdiag7.strong_codex.subprocess.run',return_value=proc):
            result,metadata,good=infer(q,Path('.'))
        self.assertFalse(good)
        self.assertIn('网络或流连接',metadata['failure_diagnostic']['categories'])
        self.assertNotIn('secret-example',result['failure_details'])
        self.assertNotIn('failure_details',metadata)


if __name__=='__main__':unittest.main()
