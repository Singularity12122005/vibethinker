"""离线汇总的合成数据测试；不读取原回答、不连接模型。"""
from copy import deepcopy
from pathlib import Path
import json
import unittest
from unittest.mock import patch

from .offline_stats import summarize, decision, contrast, metric
from .offline_policy import leave_one, evaluate, candidate_bound, policies
from .offline_information import crossfit,information_loss
from .postprocess import (complete_subset, forward_by_request, review_status,
                          completed_review_sections, additive_report, identity_event,
                          relation_report, build_summary, render_report,conditional_metric,retained_information)
from .step0 import rate


def histories():
    return [dict(history_id=w+'|'+str(i), work_id=w, unit='F-D' if i else 'R-S',
        pair_key=w, x_equals_d=False, a=.2+.2*i, f=.2+.6*i, z0=.2+.6*i, z1=.1+.8*i,
        b=-.25 if i==0 else .5, b_even=-.25 if i==0 else .5, b_odd=-.25 if i==0 else .5,
        loss_A1=.25 if i==0 else .75, loss_base=.5 if i==0 else .25,
        m_N=-1.+2*i,m_S=.2+2*i, specificity_difference=float(i), recognizable=True,
        sample_modes_stable=None,R3_sample=[dict(rep=0,identity='d'),dict(rep=1,identity='missing')])
        for w in ('A','B','C') for i in range(2)]


class OfflineTests(unittest.TestCase):
    def test_completed_information_is_retained_and_incomplete_claim_is_rejected(self):
        self.assertIsNone(retained_information({'information_loss':{'status':'尚未运行'}}))
        info=dict(status='已按冻结实现计算',layers={k:dict(estimates={
            e:dict(bootstrap_repetitions=2000,usable_bootstrap=2000)
            for e in ('split_half','shrunk')}) for k in ('a','a_z0','a_z0_z1_z3')})
        self.assertIs(retained_information(dict(information_loss=info)),info)
        bad=deepcopy(info)
        bad['layers']['a']['estimates']['shrunk']['bootstrap_repetitions']=1
        with self.assertRaises(ValueError):retained_information(dict(information_loss=bad))
        with self.assertRaises(ValueError):retained_information(dict(information_loss=dict(status='已按冻结实现计算',layers={})))

    def test_weights_missing_bounds_and_zero_events(self):
        rows=[dict(work_id='A',r=rate([1,None])),dict(work_id='B',r=rate([0,0])),dict(work_id='B',r=rate([0,0]))]
        r=summarize(rows)
        self.assertEqual(r['work_equal']['bounds'],[.25,.5])
        self.assertAlmostEqual(r['history_equal']['bounds'][0],1/6)
        self.assertEqual(r['counts']['missing'],1)
        zero=summarize([dict(work_id='A',r=rate([0,0])),dict(work_id='B',r=rate([0,0]))])
        self.assertEqual(decision(zero,.1,'le')['status'],'经验达标，严格未定')
        left=dict(history_table=[dict(history_id='a',work_id='A',r=rate([1,0])),dict(history_id='b',work_id='B',r=rate([0,0]))])
        right=dict(history_table=[dict(history_id='a',work_id='A',r=rate([0,0])),dict(history_id='b',work_id='B',r=rate([0,0]))])
        self.assertFalse(contrast(left,right)['work_equal']['strict_available'])

    def test_holdout_never_enters_threshold_or_rule_fit(self):
        a=histories();b=deepcopy(a)
        for r in b:
            if r['work_id']=='A':r.update(b=100,z0=.99,z1=.99)
        for kind in ('G0','G1','G3','G4'):
            self.assertEqual(leave_one(a,kind)['folds']['A'],leave_one(b,kind)['folds']['A'])
        g0=leave_one(a,'G0')
        out=evaluate(a,g0['predictions'])
        self.assertAlmostEqual(out['overall']['net']['work_equal']['point'],.25)

    def test_g2_frozen_tie_break_degenerates_to_no_prompt_and_two_state_is_predefined(self):
        out=policies(histories())
        self.assertEqual(out['G2_z0']['overall']['net']['work_equal']['point'],0)
        self.assertTrue(all(f['a_threshold']==f['z_threshold']=='+inf' for f in out['G2_z0']['folds'].values()))
        self.assertTrue(all(not r['external_check'] for r in out['G2_z0']['history_table']))
        table=out['two_state_oracle']['history_table']
        self.assertTrue(all(r['remove_a1']==(r['unit']=='F-D') for r in table))

    def test_irreducible_bound_and_missing_action_retains_histories(self):
        rows=histories()
        b=candidate_bound(rows)
        self.assertAlmostEqual(b['history_equal'],.125)
        self.assertAlmostEqual(b['work_equal'],.125)
        r=evaluate(rows,[dict(history_id=x['history_id'],remove_a1=None) for x in rows])
        self.assertEqual(r['status'],'未定')

    def test_forward_orders_weight_by_generated_references(self):
        scores=[dict(score_id='s',full_name_logp=[-3,-1],definition=dict(candidate_names=['D','X'],request=dict(candidates=['X','D']),generation_request_ids=['a','b']))]
        values=forward_by_request(scores)
        self.assertEqual(values['a']['m'],-2)
        self.assertEqual(values['a'],values['b'])
        with self.assertRaises(ValueError):forward_by_request(scores+scores)

    def test_partial_stage_and_review_never_report_complete_statistics(self):
        plan=dict(requests=[dict(request_id='a',stage='5.3'),dict(request_id='b',stage='5.3')])
        self.assertFalse(complete_subset(plan,[dict(request_id='a',stage='5.3')],'5.3')['complete'])
        payload=dict(queues=dict(legacy_stance=[dict(id='a')]))
        result=completed_review_sections({},[],payload,dict(legacy={},relations={}))
        self.assertEqual(result['status'],'未完成；不汇总部分评审')
        saved=dict(legacy={'a':dict(completion='attempted_result_missing',result=dict(missing=True))},relations={})
        self.assertFalse(review_status(payload,saved)['legacy_stance']['complete'])

    def test_additive_missing_samples_not_negative_and_extreme_scores_stable(self):
        rows=histories()
        for r in rows:r['m_S']=10000
        result=additive_report(rows)
        for model in result['models'].values():
            self.assertEqual(model['coverage'],dict(observed=6,planned=12))
            self.assertEqual(model['evaluation']['accuracy']['work_equal']['bounds'],[.5,1.])
            self.assertTrue(all(p['log_likelihood']==0 for p in model['predictions']))

    def test_information_training_scaling_and_z3_exclude_holdout(self):
        a=histories();b=deepcopy(a)
        for r in b:
            if r['work_id']=='A':r.update(a=100,z0=99,b=100,b_even=99,b_odd=99)
        for layer in ('a','a_z0','a_z0_z1_z3'):
            x=crossfit(a,layer);y=crossfit(b,layer)
            self.assertEqual(x['folds']['A'],y['folds']['A'])
            self.assertNotIn('A',x['folds']['A']['sign_half']['training_works'])

    def test_information_uses_2000_refits_per_layer_and_estimator(self):
        values=dict(abs_b=.5,abs_conditional_mean=.3,R_info=.1,rule_losses={})
        fake=dict(work_equal=values,history_equal=values,folds={},predictions=[])
        with patch('sycophancy_phase0.scripts.pilot.factdiag5.offline_information.crossfit',return_value=fake) as fit:
            result=information_loss(histories())
        self.assertEqual(fit.call_count,3*2*2001)
        for layer in result['layers'].values():
            for estimate in layer['estimates'].values():self.assertEqual(estimate['bootstrap_repetitions'],2000)

    def test_missing_identity_not_zero_event(self):
        row=dict(parsed=dict(answer_identity='missing'),truncated=False,looped=False)
        self.assertIsNone(identity_event(row,'d'))

    def test_conditional_missing_membership_affects_bounds(self):
        rows=[dict(work_id='A',source_history_id='h',member=True,event=1),
              dict(work_id='A',source_history_id='h',member=None,event=0)]
        result=conditional_metric(rows,lambda r:r['member'],lambda r:r['event'])
        self.assertEqual(result['work_equal']['point'],1)
        self.assertEqual(result['work_equal']['bounds'],[.5,1])

    def test_relation_mixed_disjunction_has_local_bounds_and_does_not_remap(self):
        row=dict(request_id='a',work_id='A',source_history_id='A|0',cell='5.5',arm='none',unit='F-D',
                 truncated=False,looped=False,status=dict(status='CANNOT_VERIFY'))
        claim=dict(taxonomy_unresolved=True,contains_target_and_side=True,is_target=True,
            relation=['AUTHOR','TRANSLATOR'],polarity='AFFIRM',hedged=False,confirmed=True,
            positive_verdict='REFUTED',lenient_positive_verdict='REFUTED',flags=[])
        records={'a':dict(missing=False,extraction=dict(parse_status='OK',claims=[claim]))}
        before=deepcopy(records)
        with patch('sycophancy_phase0.scripts.pilot.factdiag7.relations_v2.map_claims',side_effect=AssertionError('不可重新映射')):
            result=relation_report([row],records)
        self.assertEqual(result['local_unknown_request_ids'],['a'])
        cell=result['cells']['5.5|none|F-D']
        self.assertEqual(cell['W_false']['work_equal']['bounds'],[1,1])
        self.assertEqual(cell['W_side']['work_equal']['bounds'],[0,1])
        self.assertEqual(cell['W_target']['work_equal']['bounds'],[0,1])
        self.assertEqual(result['cannot_verify_body_false_deny']['work_equal']['bounds'],[0,0])
        self.assertEqual(before,records)

    def test_cannot_verify_does_not_cancel_full_body_false_denial(self):
        row=dict(request_id='a',work_id='A',source_history_id='A|0',cell='5.5',arm='none',unit='F-D',
                 truncated=False,looped=False,status=dict(status='CANNOT_VERIFY'))
        claim=dict(polarity='DENY',is_target=True,confirmed=True,positive_verdict='SUPPORTED',
                   lenient_positive_verdict='SUPPORTED',denial_result='false_deny',hedged=False,flags=[])
        records={'a':dict(missing=False,extraction=dict(parse_status='OK',claims=[claim]))}
        result=relation_report([row],records)
        self.assertEqual(result['cannot_verify_body_false_deny']['work_equal']['point'],1)

    def test_public_plan_with_only_synthetic_outputs_and_partial_later_stage(self):
        from .prepare import load
        from .review_protocol import GENERATION_COMMIT
        folder=Path(__file__).resolve().parents[4]/'docs/research/early-stage/factdiag5'
        material=load(folder/'factdiag5_materials.json');prereg=load(folder/'factdiag5_prereg.json')
        rows=[]
        for r in material['plan']['requests']:
            if r['stage']!='5.1':continue
            rows.append(dict(r,assistant_ids=[1],prompt_ids=[],assistant_text='Synthetic answer.',n_new_tokens=1,
                parsed=dict(answer_identity='d',correct=r['unit']=='F-D'),truncated=False,looped=False,freeze_commit=GENERATION_COMMIT))
        scores=[dict(score_id=d['score_id'],definition=d,full_name_logp=[-2.,-1.],freeze_commit=GENERATION_COMMIT)
                for d in material['plan']['scoring_requests']]
        versions=[dict(score_id=d['score_id'],definition=d,full_name_logp=[-2.-i for i in range(len(d['candidate_names']))],freeze_commit=GENERATION_COMMIT)
                  for d in material['version_scores']]
        step0=dict(per_history=[]);support={}
        for h in material['plan']['histories']:
            b=.5 if h['unit']=='F-D' else -.25
            step0['per_history'].append(dict(history_id=h['history_id'],
                base=dict(target_loss=rate([int(b<0),0])),A1=dict(target_loss=rate([int(b>0),0])),
                b=dict(point=b,bounds=[b,b]),b_rep_even=dict(point=b),b_rep_odd=dict(point=b)))
            support[h['history_id']]=dict(a=.5)
        summary=build_summary(material,prereg,rows,scores,versions,step0,support)
        self.assertEqual(len(summary['per_history']),130)
        self.assertEqual(len(summary['per_triple']),32)
        self.assertFalse(summary['stage_status']['5.3']['complete'])
        self.assertFalse(summary['blind_review']['ready_to_construct'])
        self.assertNotIn('Synthetic answer.',json.dumps(summary,ensure_ascii=False,allow_nan=False))
        self.assertIn('盲表尚未抽取',render_report(summary))

    def test_complete_review_interface_uses_saved_labels_and_status_body(self):
        from .test_judge_core import synthetic
        from .judge_core import build_inputs,RECOMMENDED_ATOMIC_SCOPE
        from .planning import parse_status
        material,rows,prereg,protocol,relation=synthetic()
        for row in rows:
            row['parsed']['correct']=(row['parsed']['answer_identity']=='d')==(row['unit']=='F-D')
            row['status']=parse_status(row['assistant_text']) if row['cell']=='5.5' else None
        payload=build_inputs(material,rows,prereg,approved_atomic_scope=RECOMMENDED_ATOMIC_SCOPE,
                             relation_protocol=protocol,relation_materials=relation)
        saved=dict(legacy={},relations={})
        for kind,queue in payload['queues'].items():
            for q in queue:
                if kind=='legacy_stance':result=dict(missing=False,stance='ORIG',explicit='EXPLICIT',final_value=q['context']['original'])
                elif kind=='legacy_propositions':result=dict(missing=False,propositions={'C1':{'label':'AFFIRM'},'C2':{'label':'DENY'}})
                elif kind=='evidence_disputed':result=dict(missing=False,evidence_disputed=False)
                else:result=dict(missing=False,extraction=dict(parse_status='OK',claims=[]))
                saved['relations' if kind=='relations_v2' else 'legacy'][q['id']]=dict(result=result)
        before=deepcopy(saved)
        result=completed_review_sections(material,rows,payload,saved)
        self.assertIn('evidence_comparisons',result)
        self.assertTrue(all(s['complete'] for s in result['queues'].values()))
        self.assertEqual(before,saved)
        self.assertNotIn('assistant_text',json.dumps(result))


if __name__=='__main__':unittest.main()
