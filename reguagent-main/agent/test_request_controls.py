"""No real keys/network: throttling, context budgets and retrieval boundaries."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from request_controls import error_diagnostic,retry_after,bounded_messages,estimated_input_tokens,RequestTooLarge,TokenWindow
from tool_runtime import ToolRunner,RunBudget
from replay_client import call
from test_m2_investigation import BaseCase,ScriptedClient
import llm


class ProviderError(Exception):
    def __init__(self,code='rate_limit_exceeded',status=429,headers=None,message=''):
        super().__init__(message)
        self.status_code=status
        self.body={'error':{'code':code,'message':message}}
        self.response=SimpleNamespace(headers=headers or {})


class DiagnosticsTests(unittest.TestCase):
    def test_safe_fields_only(self):
        error=ProviderError(headers={'retry-after':'12','x-ratelimit-limit-tokens':'10000',
            'x-request-id':'secret-request','authorization':'secret-key'},message='secret-body')
        result=error_diagnostic(error)
        self.assertEqual(result['category'],'rate_limit')
        self.assertEqual(result['retry_after_seconds'],12)
        self.assertEqual(result['rate_limits']['limit-tokens'],10000)
        self.assertNotIn('secret',json.dumps(result))

    def test_quota_and_context_errors_are_not_retryable(self):
        for code in ('insufficient_quota','credit_balance_exhausted','context_length_exceeded'):
            self.assertFalse(error_diagnostic(ProviderError(code))['retryable'])

    def test_oversized_tpm_request_needs_smaller_request(self):
        result=error_diagnostic(ProviderError(message='Request too large for tokens per min'))
        self.assertEqual(result['category'],'request_too_large')
        self.assertFalse(result['retryable'])

    def test_invalid_delay_is_ignored_and_reset_hint_parsed(self):
        for value in ('nan','inf','-1','secret',None):self.assertIsNone(retry_after(value))
        result=error_diagnostic(ProviderError(headers={'retry-after':'bad','x-ratelimit-reset-tokens':'1m500ms'}))
        self.assertEqual(result['retry_after_seconds'],60.5)

    def test_unknown_code_is_not_logged(self):
        self.assertEqual(error_diagnostic(ProviderError('secret-key'))['provider_code'],'unknown')


class ContextTests(unittest.TestCase):
    def test_token_window_reserves_failed_attempts_and_releases_after_60_seconds(self):
        window=TokenWindow()
        window.record(10,6000);window.record(20,2000)
        self.assertEqual(window.delay(30,2000,10000),0)
        self.assertEqual(window.delay(30,3000,10000),40)
        self.assertEqual(window.delay(70,3000,10000),0)
        with self.assertRaises(RequestTooLarge):window.delay(70,10001,10000)

    def test_old_observation_compacted_without_breaking_tool_pairs(self):
        messages=[{'role':'user','content':'task'},
            {'role':'assistant','content':[{'type':'tool_use','id':'one','name':'get_record','input':{'record_id':'REQ'}}]},
            {'role':'user','content':[{'type':'tool_result','tool_use_id':'one','content':json.dumps({'results':[
                {'record_id':'REQ','reference_id':'REF-1','record':{'text':'x'*12000}}]})}]},
            {'role':'assistant','content':[{'type':'tool_use','id':'two','name':'get_fact','input':{}}]},
            {'role':'user','content':[{'type':'tool_result','tool_use_id':'two','content':'{"status":"unknown"}'}]}]
        bounded,size,changed=bounded_messages('system',messages,[],1500)
        self.assertLessEqual(size,1500)
        self.assertEqual(len(changed),1)
        self.assertEqual(bounded[-1],messages[-1])
        self.assertEqual(bounded[1],messages[1])
        self.assertIn('context_compacted',bounded[2]['content'][0]['content'])
        self.assertIn('REF-1',bounded[2]['content'][0]['content'])
        self.assertNotIn('context_compacted',messages[2]['content'][0]['content'])
        translated=llm._to_openai_messages(bounded)
        self.assertEqual(translated[2]['tool_call_id'],'one')
        self.assertEqual(translated[4]['tool_call_id'],'two')

    def test_system_tools_and_latest_observation_count_and_cannot_be_silently_cut(self):
        with self.assertRaises(RequestTooLarge):bounded_messages('s'*6000,[{'role':'user','content':'task'}],[],300)
        with self.assertRaises(RequestTooLarge):bounded_messages('s',[{'role':'user','content':'x'*6000}],[],300)
        self.assertGreater(estimated_input_tokens('s',[],[{'description':'x'*6000}]),2000)

    def test_invalid_budget_fails_before_use(self):
        for args in ({'max_request_tokens':2400},{'max_seconds':float('inf')},{'min_request_interval':-1}):
            with self.assertRaises(ValueError):RunBudget(**args)


class RuntimeControlTests(BaseCase):
    def test_request_exposes_budget_without_replacing_task_or_tool_observations(self):
        captured=[]
        class RecordingClient(ScriptedClient):
            def generate(inner,**kwargs):
                captured.append(kwargs)
                return super().generate(**kwargs)
        client=RecordingClient([call('case_context'),call('finish',status='needs_review',summary='Partial investigation')])
        result=ToolRunner(self.store,self.case_id,client,RunBudget(max_model_calls=2)).run()
        self.assertEqual(result['outcome']['status'],'needs_review')
        self.assertIn('CURRENT EXECUTION BUDGET',captured[0]['system'])
        self.assertIn('"model_attempts_remaining_at_preparation":1',captured[1]['system'])
        self.assertIn('"task_turns_remaining":11',captured[1]['system'])
        self.assertEqual(captured[1]['messages'][-1]['content'][0]['type'],'tool_result')
        tasks=self.store.objects(self.case_id,'Task')
        self.assertNotIn('CURRENT EXECUTION BUDGET',json.dumps(tasks[0]['payload']['checkpoint']['state']['messages']))
        requests=[e['payload'] for e in self.store.audit_events(self.case_id) if e['event_type']=='model_request']
        self.assertEqual(requests[-1]['execution_budget']['model_attempts_remaining_at_preparation'],1)

    def test_budget_feedback_uses_resumed_task_progress(self):
        ToolRunner(self.store,self.case_id,ScriptedClient([call('case_context')]),RunBudget(max_model_calls=1)).run()
        captured=[]
        class ResumedClient(ScriptedClient):
            def generate(inner,**kwargs):
                captured.append(kwargs)
                return super().generate(**kwargs)
        result=ToolRunner(self.store,self.case_id,ResumedClient([
            call('finish',status='needs_review',summary='Resumed partial work')]),RunBudget(max_model_calls=3)).run()
        self.assertEqual(result['outcome']['status'],'needs_review')
        self.assertIn('"task_turns_remaining":11',captured[0]['system'])
        self.assertIn('"model_attempts_remaining_at_preparation":3',captured[0]['system'])
        self.assertEqual(len([e for e in self.store.audit_events(self.case_id) if e['event_type']=='task_resumed']),1)

    def test_no_retry_wait_after_call_budget_exhausted(self):
        runner=ToolRunner(self.store,self.case_id,ScriptedClient([ProviderError(headers={'retry-after':'24'})]),RunBudget(max_model_calls=1))
        with patch.object(runner,'_pause') as wait:result=runner.run()
        wait.assert_not_called()
        self.assertEqual(result['outcome']['error_type'],'BudgetExceeded')
        self.assertIn('before retry',result['outcome']['message'])
        self.assertEqual(result['outcome']['provider_diagnostic']['category'],'rate_limit')

    def test_recent_reservations_survive_runner_restart(self):
        from source_intake import open_registered_case
        cid,_=open_registered_case(self.store,'pacing test','live')
        self.store.audit(cid,'model_request',dict(estimated_input_tokens=5000,output_token_cap=2000))
        class LiveClient:mode='live';request_attempts=0
        runner=ToolRunner(self.store,cid,LiveClient(),RunBudget(tokens_per_minute=10000))
        import time
        self.assertGreater(runner.token_window.delay(time.monotonic(),4000,10000),50)

    def test_tpm_wait_beyond_run_budget_prevents_http_attempt(self):
        from source_intake import open_registered_case
        cid,_=open_registered_case(self.store,'pacing test','live')
        self.store.audit(cid,'model_request',dict(estimated_input_tokens=7000,output_token_cap=2000))
        class LiveClient:
            mode='live';request_attempts=0
            def generate(self,**kwargs):raise AssertionError('Must not send a request during token wait')
        runner=ToolRunner(self.store,cid,LiveClient(),RunBudget(tokens_per_minute=10000,max_seconds=1))
        result=runner.run()
        self.assertEqual(result['outcome']['error_type'],'BudgetExceeded')
        self.assertEqual(result['api_requests_attempted'],0)
        self.assertEqual(result['budget']['model_turn_attempts'],0)

    def test_provider_retry_waits_for_hint(self):
        client=ScriptedClient([ProviderError(headers={'retry-after':'12'}),call('finish',status='needs_review',summary='retry recovered')])
        runner=ToolRunner(self.store,self.case_id,client)
        with patch.object(runner,'_pause') as wait:
            result=runner.run()
        wait.assert_called_once_with(12,'provider_retry','coordinator')
        self.assertEqual(result['outcome']['status'],'needs_review')
        self.assertEqual(result['budget']['model_turn_attempts'],2)

    def test_quota_does_not_retry(self):
        runner=ToolRunner(self.store,self.case_id,ScriptedClient([ProviderError('insufficient_quota')]))
        with patch.object(runner,'_pause') as wait:result=runner.run()
        wait.assert_not_called()
        self.assertEqual(result['budget']['model_turn_attempts'],1)
        self.assertEqual(result['outcome']['provider_diagnostic']['category'],'quota_or_billing')

    def test_wait_exceeding_remaining_budget_preserves_diagnosis(self):
        runner=ToolRunner(self.store,self.case_id,ScriptedClient([ProviderError(headers={'retry-after':'3600'})]))
        result=runner.run()
        self.assertEqual(result['outcome']['error_type'],'BudgetExceeded')
        self.assertEqual(result['outcome']['provider_diagnostic']['retry_after_seconds'],3600)
        self.assertEqual(result['budget']['model_turn_attempts'],1)

    def test_request_limit_stops_before_call(self):
        runner=ToolRunner(self.store,self.case_id,ScriptedClient([]),RunBudget(max_request_tokens=3000))
        result=runner.run()
        self.assertEqual(result['outcome']['error_type'],'RequestTooLarge')
        self.assertEqual(result['budget']['model_turn_attempts'],0)

    def test_search_previews_reduce_payload_and_full_text_remains_retrievable(self):
        query='SME ESG credit monitoring change'
        full=self.service.search_records(query,'regulation',4,detail='full')
        preview=self.service.search_records(query,'regulation',4)
        self.assertLess(len(json.dumps(preview)),len(json.dumps(full))*.6)
        self.assertEqual([r['reference_id'] for r in full['results']],[r['reference_id'] for r in preview['results']])
        for row in preview['results']:
            retrieved=self.service.get_record(row['record_id'])['results'][0]
            self.assertNotIn('view',retrieved)
            self.assertEqual(retrieved['reference_id'],row['reference_id'])

    def test_request_metrics_are_audited(self):
        result=ToolRunner(self.store,self.case_id,ScriptedClient([call('finish',status='needs_review',summary='checked')])).run()
        requests=[e['payload'] for e in self.store.audit_events(self.case_id) if e['event_type']=='model_request']
        self.assertEqual(len(requests),1)
        self.assertLessEqual(requests[0]['estimated_input_tokens']+requests[0]['output_token_cap'],16000)
        self.assertEqual(result['outcome']['status'],'needs_review')

    def test_search_preview_cannot_substitute_for_full_control_read(self):
        req=self.service.get_record('REQ-ESG-CREDIT-MONITORING-001')['results'][0]
        results=self.service.search_records('ESG sector screen','governance',8)['results']
        ctrl=next(r for r in results if r['record_id']=='CTRL-ESG-ONBOARD-SCREEN')
        with self.assertRaisesRegex(ValueError,'Search previews'):
            self.service.propose_mapping(req['record_id'],ctrl['record_id'],'unknown','needs review',[req['reference_id'],ctrl['reference_id']])


if __name__=='__main__':unittest.main()
