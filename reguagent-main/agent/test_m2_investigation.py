"""Persistence, permissions, answer recovery and explicit replay integration checks."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from project_paths import PROJECT_ROOT,DATASET_ROOT
from dataset_runtime import load_runtime
from case_store import CaseStore,digest
from source_intake import open_registered_case,register_local_snapshot,compare_versions
from investigation_tools import InvestigationTools,FACT_ID,SCHEMAS,PERMISSIONS,tool_definitions
from tool_contracts import validate
from tool_runtime import ToolRunner,RunBudget
from replay_client import ReplayClient,call,history
from run_case import GOAL,run,demo_replay

ANSWER=json.loads((PROJECT_ROOT/'materials/esg_demo/energy_answer.synthetic.json').read_text())


class BaseCase(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name,'cases.sqlite3')
        self.store=CaseStore(self.path)
        self.case_id,_=open_registered_case(self.store,GOAL,'replay')
        self.service=InvestigationTools(self.store,self.case_id,'bank_investigator')
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def question(self):
        self.service.get_fact(FACT_ID)
        return self.service.request_question(FACT_ID,'Quantify the energy-data collection population')


class PersistenceTests(BaseCase):
    def test_case_dedup_and_isolation(self):
        again,created=open_registered_case(self.store,GOAL,'replay')
        self.assertEqual(again,self.case_id);self.assertFalse(created)
        other,_=open_registered_case(self.store,GOAL,'replay',nonce='second')
        self.assertNotEqual(other,self.case_id)
        a=self.store.put(self.case_id,'Action','draft-task',{'title':'Unapproved draft'})
        b=self.store.put(other,'Action','draft-task',{'title':'Unapproved draft'})
        self.assertNotEqual(a['object_id'],b['object_id'])
        self.assertEqual(self.store.case(self.case_id)['snapshot_dates'],['2026-06-30'])

    def test_input_copy_is_frozen_and_hash_checked(self):
        files=self.store.inputs(self.case_id);files['01_entity/bank_profile.json']['snci_status']=True
        self.assertIs(self.store.inputs(self.case_id)['01_entity/bank_profile.json']['snci_status'],False)
        with self.store.db:self.store.db.execute('UPDATE cases SET inputs_json=? WHERE case_id=?',(json.dumps(files),self.case_id))
        with self.assertRaises(ValueError):self.store.inputs(self.case_id)

    def test_all_domain_objects_version_and_audit_survive_restart(self):
        for kind in ('Finding','Question','GapAssessment','PlanVersion','Action','Evidence'):
            self.store.put(self.case_id,kind,'versioned',{'note':'version 1'})
            self.store.put(self.case_id,kind,'versioned',{'note':'version 2'})
        self.store.close();self.store=CaseStore(self.path)
        for kind in ('Finding','Question','GapAssessment','PlanVersion','Action','Evidence'):
            self.assertEqual(self.store.get(self.case_id,kind,'versioned')['version'],2)
            self.assertEqual(len(self.store.objects(self.case_id,kind,current=False)),2)
        self.assertTrue(self.store.verify_audit(self.case_id))

    def test_no_approval_states_or_baseline_database(self):
        with self.assertRaises(ValueError):self.store.set_status(self.case_id,'closed','model says so')
        with self.assertRaises(ValueError):self.store.put(self.case_id,'Action','a',{'human_review_status':'approved'})
        with self.assertRaises(ValueError):CaseStore(DATASET_ROOT/'forbidden.sqlite3')

    def test_audit_tampering_is_detected(self):
        self.assertTrue(self.store.verify_audit(self.case_id))
        with self.store.db:self.store.db.execute('UPDATE audit_events SET actor=? WHERE seq=(SELECT MIN(seq) FROM audit_events)',('tampered',))
        self.assertFalse(self.store.verify_audit(self.case_id))


class AnswerTests(BaseCase):
    def test_answer_needs_prior_lookup_and_explicit_owner_scope(self):
        with self.assertRaises(ValueError):self.service.request_question(FACT_ID,'Reason')
        question=self.question();self.assertEqual(question['payload']['denominator'],10000)
        self.assertEqual(question['payload']['snapshot_dates'],['2026-06-30'])
        self.assertEqual(self.question()['object_id'],question['object_id'])

    def test_wrong_units_scope_dates_owner_and_numbers_rejected(self):
        self.question();before=self.store.case(self.case_id)['revision']
        for field,value in [('value',-1),('value',float('nan')),('value',True),('denominator',32000),('numerator',6501),
            ('unit','percent_of_new_applications'),('population_product_id','PRD-OTHER'),('as_of_date','2027-01-01'),
            ('answered_by_role_id','ROLE-CIO'),('synthetic',False),('answered_by','')]:
            answer=dict(ANSWER,**{field:value})
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                self.service.answer_question(FACT_ID,answer,'bad-'+field,1)
        self.assertEqual(self.store.case(self.case_id)['revision'],before)
        self.assertEqual(self.store.get(self.case_id,'Question',FACT_ID)['status'],'open')
        self.assertIsNone(self.store.get(self.case_id,'FactPatch',FACT_ID))

    def test_patch_invalidates_only_transitive_dependencies_and_is_idempotent(self):
        self.question()
        original=self.store.put(self.case_id,'Finding','energy',{'summary':'unknown'},['fact:'+FACT_ID])
        self.store.put(self.case_id,'PlanVersion','p1',{'summary':'conditional'},['object:Finding:energy'])
        unaffected=self.store.put(self.case_id,'Finding','source',{'summary':'source unchanged'},['source:EBA'])
        result=self.service.answer_question(FACT_ID,ANSWER,'same-request',1)
        self.assertIn(original['object_id'],result['invalidated_object_ids'])
        self.assertEqual(self.store.get(self.case_id,'Finding','energy')['status'],'stale')
        self.assertEqual(self.store.get(self.case_id,'PlanVersion','p1')['status'],'stale')
        self.assertEqual(self.store.get(self.case_id,'Finding','source')['object_id'],unaffected['object_id'])
        again=self.service.answer_question(FACT_ID,ANSWER,'same-request',1)
        self.assertEqual(result,again)
        self.assertEqual(len(self.store.objects(self.case_id,'FactPatch',False)),1)
        with self.assertRaises(ValueError):self.service.answer_question(FACT_ID,dict(ANSWER,value=60,numerator=6000),'same-request',1)

    def test_answer_and_patch_roll_back_together_on_write_failure(self):
        self.question();before=self.store.case(self.case_id)['revision']
        original=self.store._put
        def fail_question(case_id,kind,*args):
            if kind=='Question':raise RuntimeError('Simulated write failure')
            return original(case_id,kind,*args)
        with patch.object(self.store,'_put',side_effect=fail_question),self.assertRaises(RuntimeError):
            self.service.answer_question(FACT_ID,ANSWER,'atomic',1)
        self.assertEqual(self.store.case(self.case_id)['revision'],before)
        self.assertIsNone(self.store.get(self.case_id,'FactPatch',FACT_ID))
        self.assertEqual(self.store.get(self.case_id,'Question',FACT_ID)['status'],'open')
        self.assertTrue(self.store.verify_audit(self.case_id))

    def test_numeric_coverage_is_attributed_not_risk_or_cost(self):
        self.question();before=self.service.compare_costs()['options']
        self.service.answer_question(FACT_ID,ANSWER,'answer',1)
        after=InvestigationTools(self.store,self.case_id,'bank_investigator')
        result=after.energy_coverage()
        self.assertEqual(result['usable_borrower_count'],6500)
        self.assertEqual(result['missing_borrower_count'],3500)
        self.assertEqual(result['evidence_status'],'owner_statement_unverified')
        self.assertEqual(after.compare_costs()['options'],before)
        self.assertNotIn('confidence_score',result)


class SourceAndToolTests(BaseCase):
    def test_missing_versions_never_produce_a_diff(self):
        result=self.service.source_versions()
        self.assertEqual(result['status'],'insufficient_source_snapshots')
        self.assertNotIn('diff',result)

    def test_local_candidate_diff_checks_hash_and_preserves_consultation_status(self):
        base=Path(self.tmp.name,'artifacts')
        older=Path(self.tmp.name,'old.txt');newer=Path(self.tmp.name,'new.txt')
        older.write_text('SYNTHETIC TEST ONLY: old consultation text')
        newer.write_text('SYNTHETIC TEST ONLY: new final text')
        source=register_local_snapshot(self.store,self.case_id,'EBA/CP/2024/02',older,base)
        duplicate=register_local_snapshot(self.store,self.case_id,'EBA/CP/2024/02',older,base)
        self.assertEqual(source['object_id'],duplicate['object_id'])
        self.assertEqual(source['payload']['status'],'consultation')
        register_local_snapshot(self.store,self.case_id,'EBA/GL/2025/01',newer,base)
        result=compare_versions(self.store,self.case_id,base)
        self.assertEqual(result['status'],'candidate_text_diff')
        self.assertEqual(result['authenticity_status'],'needs_review')
        self.assertIn('consultation_to_final',result['comparison_kind'])
        (base/source['payload']['local_artifact']).write_text('tampered')
        with self.assertRaises(ValueError):compare_versions(self.store,self.case_id,base)

    def test_source_change_invalidates_source_findings(self):
        source=self.store.put(self.case_id,'Finding','source',{'summary':'previous'},['source:SRC-ESG-EBA-GL-2025-01'])
        energy=self.store.put(self.case_id,'Finding','energy',{'summary':'not source-dependent'},['fact:'+FACT_ID])
        self.store.put(self.case_id,'SourceVersion','new',{'source_id':'SRC-ESG-EBA-GL-2025-01','status':'needs_review'})
        self.assertEqual(self.store.get(self.case_id,'Finding','source')['status'],'stale')
        self.assertEqual(self.store.get(self.case_id,'Finding','energy')['object_id'],energy['object_id'])

    def test_no_path_or_answer_leakage_and_governance_text_survives(self):
        result=self.service.search_records('ESG sector credit','governance',8,detail='full')
        text=json.dumps(result)
        self.assertNotIn('requirement_ids',text);self.assertNotIn('current_coverage',text)
        self.assertNotIn('evaluation_ground_truth',text)
        policies=[r for r in result['results'] if r['path'].endswith('policies.json')]
        self.assertTrue(any(p['record']['statements'][0]['text'] for p in policies))
        self.assertEqual(self.service.get_record('../../evaluation_ground_truth/reference_actions.json')['status'],'not_found')
        with self.assertRaises(ValueError):self.service.resolve_reference('/etc/passwd')

    def test_mapping_requires_observed_requirement_and_control(self):
        req=self.service.get_record('REQ-ESG-CREDIT-MONITORING-001')['results'][0]
        ctrl=self.service.get_record('CTRL-ESG-ONBOARD-SCREEN')['results'][0]
        with self.assertRaises(ValueError):self.service.propose_mapping(req['record_id'],ctrl['record_id'],'partial','Guess',['FAKE',req['reference_id']])
        result=self.service.propose_mapping(req['record_id'],ctrl['record_id'],'related_not_supporting','Per-application only',[req['reference_id'],ctrl['reference_id']])
        self.assertEqual(result['payload']['operating_evidence'],'unverified')
        self.assertNotIn(ctrl['record_id'],next(r for r in self.store.inputs(self.case_id)['regulatory_sources/requirements.json']['requirements'] if r['requirement_id']==req['record_id'])['control_ids'])

    def test_actual_relationships_are_returned(self):
        result=self.service.walk_dependencies('PROC-CREDIT-ORIGINATION',1)
        self.assertTrue(result['edges'])
        ids={r['record_id'] for r in result['nodes']}
        self.assertIn('SYS-LOAN-ORIG',ids)

    def test_new_task_cannot_cite_unobserved_or_replace_other_role_findings(self):
        facts=self.service.portfolio_facts()
        self.service.record_finding('bank-only','Facts','data_quality',[facts['reference_id']])
        other=InvestigationTools(self.store,self.case_id,'regulatory_analyst')
        with self.assertRaises(ValueError):other.record_finding('new','Unseen','data_quality',[facts['reference_id']])
        with self.assertRaises(PermissionError):other.record_finding('bank-only','Overwrite','data_quality',[facts['reference_id']])


class ScriptedClient:
    mode='replay';request_attempts=0
    def __init__(self,steps):self.steps=iter(steps)
    def generate(self,**kwargs):
        step=next(self.steps)
        if isinstance(step,Exception):raise step
        return step


class RuntimeTests(BaseCase):
    def test_role_permissions_reject_arbitrary_code_and_self_approval(self):
        client=ScriptedClient([call('execute_python',code='raise Exception'),call('approve_action',action_id='A'),
            call('finish',status='needs_review',summary='Unsupported actions rejected')])
        result=ToolRunner(self.store,self.case_id,client).run()
        self.assertEqual(result['outcome']['status'],'needs_review')
        errors=[a['payload'] for a in self.store.audit_events(self.case_id) if a['event_type']=='tool_result' and a['payload']['is_error']]
        self.assertEqual(len(errors),2)
        self.assertTrue(all(e['output']['error_type']=='PermissionError' for e in errors))

    def test_invalid_tool_input_is_returned_for_correction(self):
        client=ScriptedClient([call('delegate',role='invalid-role',task='test',task_key='test'),call('finish',status='needs_review',summary='Input validation checked')])
        result=ToolRunner(self.store,self.case_id,client).run()
        self.assertEqual(result['outcome']['status'],'needs_review')
        errors=[a for a in self.store.audit_events(self.case_id) if a['event_type']=='tool_result' and a['payload']['is_error']]
        self.assertEqual(len(errors),1)

    def test_open_question_cannot_be_hidden_by_completed_status(self):
        self.question()
        client=ScriptedClient([call('finish',status='completed',summary='Done'),call('finish',status='waiting',summary='Question remains open')])
        result=ToolRunner(self.store,self.case_id,client).run()
        self.assertEqual(result['outcome']['status'],'waiting')
        self.assertEqual(self.store.case(self.case_id)['status'],'waiting_for_input')

    def test_global_budget_bounds_specialist_calls(self):
        budget=RunBudget(max_model_calls=3)
        result=ToolRunner(self.store,self.case_id,ReplayClient(),budget).run()
        self.assertEqual(result['outcome']['status'],'failed')
        self.assertEqual(budget.model_calls,3)
        self.assertTrue(self.store.verify_audit(self.case_id))
        self.assertTrue(self.store.objects(self.case_id,'Task'))

    def test_repeated_no_progress_calls_stop(self):
        client=ScriptedClient([call('case_context')]*4)
        result=ToolRunner(self.store,self.case_id,client).run()
        self.assertEqual(result['outcome']['error_type'],'BudgetExceeded')
        self.assertEqual(result['budget']['model_turn_attempts'],3)

    def test_failed_run_survives_reopen(self):
        result=ToolRunner(self.store,self.case_id,ScriptedClient([RuntimeError('simulated provider failure')])).run()
        self.assertEqual(result['outcome']['status'],'failed')
        self.store.close();self.store=CaseStore(self.path)
        resumed=ToolRunner(self.store,self.case_id,ReplayClient()).run()
        self.assertEqual(resumed['outcome']['status'],'waiting')

    def test_transient_retry_is_bounded_and_recorded(self):
        client=ScriptedClient([TimeoutError('simulated'),call('finish',status='needs_review',summary='Recovered from one transient failure')])
        result=ToolRunner(self.store,self.case_id,client).run()
        self.assertEqual(result['outcome']['status'],'needs_review')
        self.assertEqual(result['budget']['model_turn_attempts'],2)

    def test_mode_mismatch_cannot_silently_fallback(self):
        class Live:mode='live'
        with self.assertRaises(ValueError):ToolRunner(self.store,self.case_id,Live())

    def test_live_missing_configuration_makes_zero_http_attempts(self):
        from llm import AnthropicToolClient
        case_id,_=open_registered_case(self.store,GOAL,'live')
        with patch.dict(os.environ,{},clear=True):
            result=ToolRunner(self.store,case_id,AnthropicToolClient()).run()
        self.assertEqual(result['outcome']['status'],'failed')
        self.assertEqual(result['api_requests_attempted'],0)
        self.assertEqual(self.store.case(case_id)['mode'],'live')

    def test_tool_call_results_are_paired_for_the_model(self):
        class ProtocolClient(ScriptedClient):
            def generate(self,**kwargs):
                messages=kwargs['messages']
                if len(messages)>1:
                    self_outer.assertEqual(messages[-1]['role'],'user')
                    self_outer.assertEqual(messages[-1]['content'][0]['type'],'tool_result')
                    self_outer.assertEqual(messages[-1]['content'][0]['tool_use_id'],messages[-2]['content'][0]['id'])
                return super().generate(**kwargs)
        self_outer=self
        result=ToolRunner(self.store,self.case_id,ProtocolClient([call('case_context'),call('finish',status='needs_review',summary='Protocol validated')])).run()
        self.assertEqual(result['outcome']['status'],'needs_review')


class ReplayIntegrationTests(BaseCase):
    def test_cold_restart_answer_and_selective_recovery(self):
        before=ToolRunner(self.store,self.case_id,ReplayClient()).run()
        self.assertEqual(before['outcome']['status'],'waiting')
        source=self.store.get(self.case_id,'Finding','source-summary')
        costs=self.store.get(self.case_id,'Finding','conditional-costs')
        self.store.close();self.store=CaseStore(self.path)
        service=InvestigationTools(self.store,self.case_id,'human_input')
        service.answer_question(FACT_ID,ANSWER,'restart-answer',1)
        after=ToolRunner(self.store,self.case_id,ReplayClient()).run()
        self.assertEqual(after['outcome']['status'],'completed')
        self.assertEqual(after['budget']['delegations'],1)
        self.assertEqual(self.store.get(self.case_id,'Finding','source-summary')['object_id'],source['object_id'])
        self.assertEqual(self.store.get(self.case_id,'Finding','conditional-costs')['object_id'],costs['object_id'])
        energy=self.store.get(self.case_id,'Finding','energy-data')
        self.assertEqual(energy['version'],3)
        self.assertIn('3500',energy['payload']['summary'])
        self.assertEqual(self.store.get(self.case_id,'Question',FACT_ID)['status'],'answered')
        self.assertTrue(self.store.verify_audit(self.case_id))
        self.assertEqual(before['api_requests_attempted']+after['api_requests_attempted'],0)

    def test_different_answer_changes_only_supported_metrics(self):
        ToolRunner(self.store,self.case_id,ReplayClient()).run()
        answer=dict(ANSWER,value=40,numerator=4000)
        self.service.answer_question(FACT_ID,answer,'counterfactual',1)
        ToolRunner(self.store,self.case_id,ReplayClient()).run()
        result=self.service.energy_coverage()
        self.assertEqual(result['missing_borrower_count'],6000)
        self.assertEqual([o['scenarios']['base']['three_year_tco_eur'] for o in self.service.compare_costs()['options']],[806818,451436,481002])
