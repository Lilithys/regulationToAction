"""Crash recovery tests with real SQLite writes; no external API calls."""
import copy
import json
import unittest
from unittest.mock import patch
from test_m2_investigation import BaseCase,ScriptedClient
from case_store import CaseStore,encode
from investigation_tools import PERMISSIONS,tool_definitions
from replay_client import ReplayClient,call,history
from tool_runtime import ToolRunner,RunBudget,BudgetExceeded

REQ='REQ-ESG-CREDIT-MONITORING-001'
CTRL='CTRL-ESG-ONBOARD-SCREEN'


class CheckpointTests(BaseCase):
    def restart(self):
        self.store.close();self.store=CaseStore(self.path)

    def results(self,tool=None,role=None):
        return [e['payload'] for e in self.store.audit_events(self.case_id)
                if e['event_type']=='tool_result' and (tool is None or e['payload']['tool']==tool)
                and (role is None or e['payload']['role']==role)]

    def specialist(self,client,budget=None):
        return ToolRunner(self.store,self.case_id,client,budget)._task(
            'bank_investigator','Read and persist a bounded control finding','checkpoint-test',1)

    def test_coordinator_cannot_query_or_write_domain_findings(self):
        self.assertEqual({d['name'] for d in tool_definitions('coordinator')},
                         {'case_context','delegate','finish','check_closure'})
        self.assertIn('get_record',PERMISSIONS['bank_investigator'])
        result=ToolRunner(self.store,self.case_id,ScriptedClient([
            call('get_record',record_id=REQ),
            call('finish',status='needs_review',summary='Requires specialist work')])).run()
        self.assertEqual(result['outcome']['status'],'needs_review')
        self.assertEqual(self.results('get_record')[0]['output']['error_type'],'PermissionError')

    def test_intake_alone_cannot_complete_investigation(self):
        result=ToolRunner(self.store,self.case_id,ScriptedClient([
            call('finish',status='completed',summary='Done'),
            call('finish',status='needs_review',summary='No findings yet')])).run()
        self.assertEqual(result['outcome']['status'],'needs_review')
        self.assertTrue(self.results('finish')[0]['is_error'])

    def test_specialist_must_persist_a_deliverable_to_complete(self):
        result=self.specialist(ScriptedClient([
            call('get_record',record_id=REQ),call('finish',status='completed',summary='Read only'),
            call('finish',status='needs_review',summary='Finding still needed')]))
        self.assertEqual(result['status'],'needs_review')
        self.assertTrue(self.results('finish')[0]['is_error'])

    def test_cold_restart_resumes_child_without_repeating_completed_reads(self):
        first=ToolRunner(self.store,self.case_id,ReplayClient(),RunBudget(max_model_calls=3)).run()
        self.assertEqual(first['outcome']['error_type'],'BudgetExceeded')
        child=next(t for t in self.store.objects(self.case_id,'Task')
                   if t['payload']['role']=='regulatory_analyst')
        self.assertTrue(child['payload']['checkpoint']['state']['observed'])
        self.restart()
        result=ToolRunner(self.store,self.case_id,ReplayClient()).run()
        self.assertEqual(result['outcome']['status'],'waiting',result)
        reads=self.results('get_record','regulatory_analyst')
        self.assertEqual(len(reads),1)
        self.assertEqual(reads[0]['arguments']['record_id'],REQ)
        self.assertEqual(len(self.store.objects(self.case_id,'Finding')),3)
        resumed=[e for e in self.store.audit_events(self.case_id) if e['event_type']=='task_resumed']
        self.assertEqual({e['payload']['role'] for e in resumed},{'coordinator','regulatory_analyst'})
        self.assertTrue(self.store.verify_audit(self.case_id))

    def test_cold_restart_reuses_finished_waiting_task_without_model_calls(self):
        ToolRunner(self.store,self.case_id,ReplayClient()).run()
        self.restart()
        result=ToolRunner(self.store,self.case_id,ScriptedClient([])).run()
        self.assertEqual(result['outcome']['status'],'waiting')
        self.assertTrue(result['outcome']['reused'])
        self.assertEqual(result['budget']['model_turn_attempts'],0)

    def test_mid_batch_cursor_preserves_tool_pairs_and_exactly_once_reads(self):
        batch=call('get_record',record_id=REQ)
        batch['content']+=call('get_record',record_id=CTRL)['content']
        with self.assertRaises(BudgetExceeded):
            self.specialist(ScriptedClient([batch]),RunBudget(max_tool_calls=1))
        self.restart();captured=[]
        class NextClient(ScriptedClient):
            def generate(inner,**kwargs):
                captured.append(copy.deepcopy(kwargs['messages']))
                return super().generate(**kwargs)
        self.specialist(NextClient([call('finish',status='needs_review',summary='Reads retained')]))
        self.assertEqual([r['arguments']['record_id'] for r in self.results('get_record')],[REQ,CTRL])
        self.assertEqual(len(captured),1)
        self.assertEqual(len(history(captured[0])),2)
        self.assertTrue(self.store.verify_audit(self.case_id))

    def test_finding_and_tool_cursor_rollback_together_then_resume(self):
        ref=self.service.get_record(REQ)['results'][0]['reference_id']
        original=self.store.audit;failed=False
        def fail_checkpoint(case_id,event_type,payload,**kwargs):
            nonlocal failed
            if event_type=='checkpoint_saved' and not failed and self.store.get(case_id,'Finding','atomic'):
                failed=True;raise RuntimeError('Injected checkpoint write failure')
            return original(case_id,event_type,payload,**kwargs)
        with patch.object(self.store,'audit',side_effect=fail_checkpoint),self.assertRaises(RuntimeError):
            self.specialist(ScriptedClient([call('get_record',record_id=REQ),
                call('record_finding',key='atomic',summary='Provisional text review',category='source',reference_ids=[ref])]))
        self.assertIsNone(self.store.get(self.case_id,'Finding','atomic'))
        self.assertEqual(self.results('record_finding'),[])
        self.restart()
        result=self.specialist(ScriptedClient([call('finish',status='completed',summary='Finding saved')]))
        self.assertEqual(result['status'],'completed')
        self.assertEqual(self.store.get(self.case_id,'Finding','atomic')['version'],1)
        self.assertEqual(len(self.results('record_finding')),1)
        self.assertEqual(len(self.results('get_record')),1)
        self.assertTrue(self.store.verify_audit(self.case_id))

    def test_completed_child_survives_parent_commit_failure(self):
        original=self.store.audit;failed=False
        def fail_parent(case_id,event_type,payload,**kwargs):
            nonlocal failed
            if event_type=='tool_result' and payload.get('tool')=='delegate' and not failed:
                failed=True;raise RuntimeError('Injected parent commit failure')
            return original(case_id,event_type,payload,**kwargs)
        with patch.object(self.store,'audit',side_effect=fail_parent):
            first=ToolRunner(self.store,self.case_id,ReplayClient()).run()
        self.assertEqual(first['outcome']['error_type'],'RuntimeError')
        self.assertEqual(len(self.store.objects(self.case_id,'Finding')),1)
        self.assertEqual(self.results('delegate'),[])
        self.restart()
        result=ToolRunner(self.store,self.case_id,ReplayClient()).run()
        self.assertEqual(result['outcome']['status'],'waiting',result)
        self.assertEqual(len(self.results('get_record','regulatory_analyst')),1)
        self.assertEqual(self.store.get(self.case_id,'Finding','source-summary')['version'],1)
        self.assertTrue(self.results('delegate')[0]['output']['reused'])
        self.assertTrue(self.store.verify_audit(self.case_id))

    def test_new_source_revision_does_not_reuse_old_task_checkpoint(self):
        ToolRunner(self.store,self.case_id,ReplayClient(),RunBudget(max_model_calls=3)).run()
        self.store.put(self.case_id,'SourceVersion','changed',dict(source_id='SRC-ESG-EBA-GL-2025-01',status='needs_review'))
        self.restart();captured=[]
        class FreshClient(ScriptedClient):
            def generate(inner,**kwargs):
                captured.append(copy.deepcopy(kwargs['messages']))
                return super().generate(**kwargs)
        result=ToolRunner(self.store,self.case_id,FreshClient([
            call('finish',status='needs_review',summary='New source needs review')])).run()
        self.assertEqual(result['outcome']['status'],'needs_review')
        self.assertEqual(len(captured[0]),1)
        self.assertEqual(json.loads(captured[0][0]['content'])['case_revision'],2)
        self.assertFalse(any(e['event_type']=='task_resumed' for e in self.store.audit_events(self.case_id)))

    def test_checkpoint_payload_tamper_is_rejected_before_model_request(self):
        ToolRunner(self.store,self.case_id,ReplayClient(),RunBudget(max_model_calls=1)).run()
        task=self.store.objects(self.case_id,'Task')[0]
        payload=task['payload'];payload['checkpoint']['state']['messages'][0]['content']='tampered'
        with self.store.transaction():
            self.store.db.execute('UPDATE objects SET payload_json=? WHERE object_id=?',(encode(payload),task['object_id']))
        self.restart()
        result=ToolRunner(self.store,self.case_id,ScriptedClient([])).run()
        self.assertEqual(result['outcome']['error_type'],'ValueError')
        self.assertEqual(result['budget']['model_turn_attempts'],0)

    def test_no_sqlite_write_transaction_is_held_during_model_calls(self):
        store=self.store
        class TransactionCheckingClient(ReplayClient):
            def generate(inner,**kwargs):
                if store.db.in_transaction:raise AssertionError('Transaction crosses model request')
                return super().generate(**kwargs)
        result=ToolRunner(self.store,self.case_id,TransactionCheckingClient()).run()
        self.assertEqual(result['outcome']['status'],'waiting',result)

    def test_nested_rollback_does_not_commit_outer_mutations(self):
        with self.assertRaises(RuntimeError):
            with self.store.transaction():
                self.store.put(self.case_id,'Finding','outer',{'summary':'Pending'})
                with self.assertRaises(ValueError):
                    with self.store.transaction():
                        self.store.put(self.case_id,'Finding','inner',{'summary':'Rolled back'})
                        raise ValueError('Inner failure')
                self.assertIsNone(self.store.get(self.case_id,'Finding','inner'))
                self.assertIsNotNone(self.store.get(self.case_id,'Finding','outer'))
                raise RuntimeError('Outer failure')
        self.assertEqual(self.store.objects(self.case_id,'Finding'),[])
        self.assertTrue(self.store.verify_audit(self.case_id))


if __name__=='__main__':unittest.main()
