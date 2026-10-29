from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from .batch5_schedule import remaining_groups, restore_handoff
from .intervention8 import get_inputs, PLAN, INPUTS, OUTPUT, SCHEDULE


class SubsetScheduleTest(unittest.TestCase):
    def fixture(self):
        entries = [dict(id=str(i), cohort='batch5_T', input_sha256='i'+str(i), prompt_sha256='p'+str(i)) for i in range(300)]
        selected = list(range(200))+list(range(277,300))
        plan = dict(entries=entries, records=[dict(views=[{'input_id':str(i)}]) for i in selected])
        limits = dict(credits={'balance':'15750.9227325000'}, primary={'usedPercent':52})
        journal = [dict(type='batch5_start', limits=limits)]; saved = {}
        for entry in entries[:256]:
            meta = dict(completion='returned', attempts=1, cli_exit_code=0, unexpected_item_types=[],
                        usage=dict(input_tokens=100, cached_input_tokens=80, output_tokens=int(entry['id'])+1),
                        input_sha256=entry['input_sha256'], prompt_sha256=entry['prompt_sha256'])
            journal += [dict(type='dispatched', id=entry['id'], cohort=entry['cohort'], prompt_sha256=entry['prompt_sha256']),
                        dict(type='result', id=entry['id'], cohort=entry['cohort'], metadata=meta)]
            saved[entry['id']] = dict(meta, cohort=entry['cohort'])
        control = dict(mode='subset_then_export_then_remaining', resume_commit='commit',
                       blocked_fetch_ids=[r['id'] for r in entries[256:288]])
        return journal, plan, saved, control

    def test_subset_first_and_remaining_relative_order(self):
        records, plan, saved, control = self.fixture()
        first, remaining = remaining_groups(plan, set(saved))
        self.assertEqual([r['id'] for r in first], [str(i) for i in range(277,300)])
        self.assertEqual([r['id'] for r in remaining], [str(i) for i in range(256,277)])
        self.assertEqual(len(first)+len(remaining)+len(saved), len(plan['entries']))

    def test_restores_original_budget_and_every_usage_record(self):
        args = self.fixture(); before = deepcopy(args)
        state = restore_handoff(*args, 'commit')
        self.assertEqual(args, before)
        self.assertEqual(state['limits']['credits']['balance'], '15750.9227325000')
        self.assertEqual(state['limits']['primary']['usedPercent'], 52)
        self.assertEqual(len(state['usage']), 256)
        self.assertEqual(sum(u['output_tokens'] for u in state['usage']), sum(range(1,257)))
        self.assertEqual(state['counts']['batch5_T'], 256)

    def test_rejects_missing_repeated_misbound_or_unproven_handoffs(self):
        for cause in ('missing','repeated','saved_usage','boundary','second_resume'):
            with self.subTest(cause=cause):
                records, plan, saved, control = self.fixture()
                if cause == 'missing': records.pop()
                if cause == 'repeated': records += deepcopy(records[-2:])
                if cause == 'saved_usage': saved['0'] = dict(saved['0'], usage={})
                if cause == 'boundary': control['blocked_fetch_ids'] = ['wrong']
                if cause == 'second_resume': records.append(dict(type='subset_first_resume'))
                with self.assertRaises(ValueError): restore_handoff(records,plan,saved,control,'commit')

    def test_remote_boundary_stops_before_dispatch_and_keeps_inputs(self):
        with TemporaryDirectory() as temp:
            out = Path(temp)/'factdiag7_20261112'; out.mkdir()
            def save(name,value):(out/name).write_text(json.dumps(value),encoding='utf-8')
            save(SCHEDULE,dict(mode='subset_then_export_then_remaining',resume_commit='commit',blocked_fetch_ids=None))
            save(PLAN,{'entries':[{'id':'next'}]}); save(INPUTS,{'next':{'id':'next','prompt':'冻结文字'}}); save(OUTPUT,{})
            original=(out/INPUTS).read_bytes()
            with self.assertRaises(RuntimeError):get_inputs(temp,['next'])
            self.assertEqual(json.loads((out/SCHEDULE).read_text())['blocked_fetch_ids'],['next'])
            self.assertEqual(get_inputs(temp,['next'],schedule_commit='commit'),[{'id':'next','prompt':'冻结文字'}])
            self.assertEqual((out/INPUTS).read_bytes(),original)
            self.assertEqual(json.loads((out/OUTPUT).read_text()),{})


if __name__ == '__main__':
    unittest.main()
