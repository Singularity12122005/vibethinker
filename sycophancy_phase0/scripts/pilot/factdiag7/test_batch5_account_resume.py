from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
import json, os, unittest

from .batch5_schedule import remaining_groups, restore_account_resume
from . import test_batch5_schedule as fixtures
from . import batch5_strong as runner


class AccountResumeTest(unittest.TestCase):
    def fixture(self):
        records,plan,saved,control=fixtures.SubsetScheduleTest().fixture()
        records.append(dict(type='subset_first_resume'))
        first,rest=remaining_groups(plan,set(saved))
        for entry in (first+rest)[:28]:
            meta=dict(completion='returned',attempts=1,cli_exit_code=0,unexpected_item_types=[],
                      usage=dict(input_tokens=100,cached_input_tokens=80,output_tokens=int(entry['id'])+1),
                      input_sha256=entry['input_sha256'],prompt_sha256=entry['prompt_sha256'])
            records.extend([dict(type='dispatched',id=entry['id'],cohort=entry['cohort'],prompt_sha256=entry['prompt_sha256']),
                            dict(type='result',id=entry['id'],cohort=entry['cohort'],metadata=meta)])
            saved[entry['id']]=dict(meta,cohort=entry['cohort'])
        records.append(dict(type='human_review_export_ready'))
        return records,plan,saved,control

    def test_reordered_prefix_keeps_budget_usage_and_pending_order(self):
        args=self.fixture();before=deepcopy(args)
        restored=restore_account_resume(*args,expected_returned=284)
        self.assertEqual(args,before)
        self.assertEqual(restored['limits']['credits']['balance'],'15750.9227325000')
        self.assertEqual(len(restored['usage']),284)
        self.assertEqual(restored['usage'][-200:],[r['metadata']['usage'] for r in args[0] if r['type']=='result'][-200:])
        self.assertEqual([r['id'] for r in args[1]['entries'] if r['id'] not in restored['completed']],list(map(str,range(261,277))))

    def test_refuses_missing_duplicate_extra_or_failed_saved_results(self):
        for cause in ('missing','duplicate','remote_extra','remote_failure','repeat_resume','reorder'):
            with self.subTest(cause=cause):
                records,plan,saved,control=self.fixture()
                if cause=='missing':records=[r for r in records if not (r['type']=='result' and r['id']=='260')]
                if cause=='duplicate':records+=deepcopy(records[1:3])
                if cause=='remote_extra':saved['outside']=dict(saved['0'])
                if cause=='remote_failure':saved['260']['completion']='attempted_result_missing'
                if cause=='repeat_resume':records.append(dict(type='account_read_resume'))
                if cause=='reorder':records[1:5]=records[3:5]+records[1:3]
                with self.assertRaises(ValueError):restore_account_resume(records,plan,saved,control,expected_returned=284)

    def test_read_failure_reconnects_without_returning_stale_limits(self):
        bad=Mock();bad.limits.side_effect=RuntimeError('只读查询失败')
        good=Mock();fresh=dict(credits={'balance':'6400'});good.limits.return_value=fresh
        factory=Mock(side_effect=[bad,good]);events=[];sleeps=[]
        account=runner.BudgetAccount(factory=factory,notify=lambda s,v:events.append(s),sleep=sleeps.append)
        account.last_limits=dict(credits={'balance':'15750.9227325'})
        self.assertEqual(account.limits(),fresh)
        self.assertEqual(events,['waiting_for_limits','limits_recovered']);self.assertEqual(sleeps,[30])
        bad.close.assert_called_once()
        self.assertEqual(runner.stop_reason('15750.9227325',fresh['credits']['balance'],[]),'余额低于6500')
        account.close()

    @unittest.skipUnless(os.name=='nt','运行器使用Windows文件锁')
    def test_saved_result_survives_quota_read_failure_and_hard_stop(self):
        normal=dict(credits={'balance':'15750.9227325'});low=dict(credits={'balance':'6400'})
        old=Mock();old.limits.side_effect=[normal,normal,RuntimeError('读取失败')]
        old.call.return_value={'data':[{'model':'gpt-6-astra'}]}
        new=Mock();new.limits.return_value=low
        factory=Mock(side_effect=[old,new]);account_class=runner.BudgetAccount
        q=dict(id='only',prompt_sha256='p',input_sha256='i')
        meta=dict(runtime={},completion='returned',attempts=1,cli_exit_code=0,unexpected_item_types=[],usage=dict(input_tokens=100,cached_input_tokens=80,output_tokens=20),input_sha256='i',prompt_sha256='p')
        plan=dict(entries=[dict(q,cohort='batch5_T')],records=[])
        with TemporaryDirectory() as temp:
            root=Path(temp);(root/'factdiag7-work').mkdir()
            with patch.dict('sys.modules',{'remote':SimpleNamespace(remote=Mock())}), \
                 patch.object(runner,'BudgetAccount',side_effect=lambda **kw:account_class(factory=factory,sleep=lambda _:None,**kw)), \
                 patch.object(runner.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='Logged in using ChatGPT',stderr='')), \
                 patch.object(runner,'fetch',side_effect=[plan,[q]]), \
                 patch.object(runner,'send_result') as save, \
                 patch.object(runner.runtime,'infer',return_value=(dict(runtime={}),deepcopy(meta),True)) as infer:
                runner.run(temp)
            records=[json.loads(line) for line in (root/'factdiag7-work/strong/batch5_records.jsonl').read_text().splitlines()]
            types=[r['type'] for r in records]
            self.assertEqual(types.count('dispatched'),1);self.assertEqual(types.count('result'),1)
            self.assertLess(types.index('result'),types.index('waiting_for_limits'))
            result=json.loads((root/'factdiag7-work/strong/batch5_summary.json').read_text())
            self.assertEqual(result['status'],'paused');self.assertEqual(result['stop_reason'],'余额低于6500')
            self.assertEqual(result['counts']['batch5_T'],1);self.assertEqual(result['usage']['output_tokens'],20)
            save.assert_called_once();infer.assert_called_once()


if __name__=='__main__':unittest.main()
