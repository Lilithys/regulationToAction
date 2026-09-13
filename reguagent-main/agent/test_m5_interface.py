"""T21/T22: the read-only view adapter and the minimal JSON API server built on it."""
import base64
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from project_paths import PROJECT_ROOT
from case_store import CaseStore
from source_intake import open_registered_case
import run_case
import view_adapter
import api_server

GOAL=run_case.GOAL
DEMO=PROJECT_ROOT/'materials/esg_demo'
ANSWER=json.loads((DEMO/'energy_answer.synthetic.json').read_text())


class ViewAdapterBase(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name,'cases.sqlite3')
        self.store=CaseStore(self.path)
        self.artifact_root=Path(self.tmp.name,'evidence_artifacts')
    def tearDown(self):self.store.close();self.tmp.cleanup()


class CaseViewTests(ViewAdapterBase):
    def setUp(self):
        super().setUp()
        self.case_id,_=open_registered_case(self.store,GOAL,'replay')
        run_case.run(self.store,self.case_id)

    def test_case_overview_matches_live_case_row(self):
        overview=view_adapter.case_overview(self.store,self.case_id)
        case=self.store.case(self.case_id)
        self.assertEqual(overview['case_id'],self.case_id)
        self.assertEqual(overview['status'],case['status'])
        self.assertEqual(overview['revision'],case['revision'])
        self.assertTrue(overview['audit_chain_valid'])

    def test_unknown_case_raises_key_error(self):
        with self.assertRaises(KeyError):view_adapter.case_overview(self.store,'CASE-does-not-exist')

    def test_investigation_summary_reports_tasks_and_findings(self):
        summary=view_adapter.investigation_summary(self.store,self.case_id)
        self.assertGreater(len(summary['tasks']),0)
        self.assertGreater(len(summary['findings']),0)
        self.assertTrue(any(q['owner_role_id'] for q in summary['open_questions']))

    def test_plan_and_action_view_exposes_the_drafted_action(self):
        view=view_adapter.plan_and_action_view(self.store,self.case_id)
        self.assertEqual(len(view['plans']),1)
        self.assertEqual(len(view['actions']),1)
        self.assertEqual(view['actions'][0]['status'],'draft')
        self.assertEqual(view['actions'][0]['acceptance_status'],'proposed')

    def test_audit_log_is_chronological_and_labels_actor_type(self):
        log=view_adapter.audit_log(self.store,self.case_id)
        self.assertEqual([e['seq'] for e in log],sorted(e['seq'] for e in log))
        self.assertTrue(any(e['actor_type']=='application' for e in log))


class QueueLifecycleTests(ViewAdapterBase):
    """Drives one case through the exact fact->response->evidence->closure sequence
    entirely via the generic resolve_queue_item dispatcher, as a real client would."""
    def setUp(self):
        super().setUp()
        self.case_id,_=open_registered_case(self.store,GOAL,'replay')
        before=run_case.run(self.store,self.case_id)
        self.assertEqual(before['outcome']['status'],'waiting')

    def test_fact_and_response_items_are_both_pending_after_the_first_run(self):
        queue=view_adapter.pending_queue(self.store,self.case_id,self.artifact_root)
        sections={i['section'] for i in queue}
        self.assertEqual(sections,{'fact','response'})

    def test_resolving_the_fact_item_advances_the_case_and_clears_it(self):
        fact=next(i for i in view_adapter.pending_queue(self.store,self.case_id,self.artifact_root) if i['section']=='fact')
        result=view_adapter.resolve_queue_item(self.store,self.case_id,fact['id'],ANSWER)
        self.assertEqual(result['kind'],'answer_question')
        run_case.run(self.store,self.case_id)
        self.assertFalse(any(i['section']=='fact' for i in view_adapter.pending_queue(self.store,self.case_id,self.artifact_root)))

    def test_full_lifecycle_through_the_generic_dispatcher_reaches_closure(self):
        fact=next(i for i in view_adapter.pending_queue(self.store,self.case_id,self.artifact_root) if i['section']=='fact')
        view_adapter.resolve_queue_item(self.store,self.case_id,fact['id'],ANSWER)
        run_case.run(self.store,self.case_id)

        response=next(i for i in view_adapter.pending_queue(self.store,self.case_id,self.artifact_root) if i['section']=='response')
        who=response['who'];action_key=response['key']
        view_adapter.resolve_queue_item(self.store,self.case_id,response['id'],dict(accepted_by_role_id=who))

        view_adapter.submit_evidence_item(self.store,self.case_id,action_key,'design','control_design',
            DEMO/'control_design.synthetic.txt',who,self.artifact_root)
        design=next(i for i in view_adapter.pending_queue(self.store,self.case_id,self.artifact_root) if i['section']=='evidence')
        view_adapter.resolve_queue_item(self.store,self.case_id,design['id'],dict(decision='verified',decided_by_role_id=who))

        view_adapter.submit_evidence_item(self.store,self.case_id,action_key,'test','control_effectiveness_test',
            DEMO/'control_effectiveness_test.synthetic.txt',who,self.artifact_root)
        test=next(i for i in view_adapter.pending_queue(self.store,self.case_id,self.artifact_root) if i['section']=='evidence')
        view_adapter.resolve_queue_item(self.store,self.case_id,test['id'],dict(decision='verified',decided_by_role_id=who))

        closure=next(i for i in view_adapter.pending_queue(self.store,self.case_id,self.artifact_root) if i['section']=='closure')
        result=view_adapter.resolve_queue_item(self.store,self.case_id,closure['id'],dict(decided_by_role_id=who))
        self.assertEqual(result['result']['status'],'verified')
        self.assertEqual(view_adapter.pending_queue(self.store,self.case_id,self.artifact_root),[])

    def test_resolve_rejects_malformed_item_id(self):
        with self.assertRaises(ValueError):view_adapter.resolve_queue_item(self.store,self.case_id,'no-colon-here',{})

    def test_resolve_rejects_unknown_section(self):
        with self.assertRaises(ValueError):view_adapter.resolve_queue_item(self.store,self.case_id,'made-up:some-key',{})

    def test_fact_resolve_revalidates_the_answer_schema_server_side(self):
        fact=next(i for i in view_adapter.pending_queue(self.store,self.case_id,self.artifact_root) if i['section']=='fact')
        with self.assertRaises(ValueError):view_adapter.resolve_queue_item(self.store,self.case_id,fact['id'],dict(value=-1))

    def test_response_resolve_requires_role_field(self):
        response=next(i for i in view_adapter.pending_queue(self.store,self.case_id,self.artifact_root) if i['section']=='response')
        with self.assertRaises(ValueError):view_adapter.resolve_queue_item(self.store,self.case_id,response['id'],{})


class ApiServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name,'cases.sqlite3')
        store=CaseStore(self.path)
        self.case_id,_=open_registered_case(store,GOAL,'replay')
        run_case.run(store,self.case_id)
        store.close()
        self.server=api_server.make_server(self.path,port=0)
        self.port=self.server.server_address[1]
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.thread.join(timeout=5)
        self.server.case_store.close();self.server.server_close();self.tmp.cleanup()

    def _url(self,path):return f'http://127.0.0.1:{self.port}{path}'

    def _get(self,path):
        try:
            with urllib.request.urlopen(self._url(path)) as resp:return resp.status,json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            with exc:return exc.code,json.loads(exc.read())

    def _post(self,path,body):
        data=json.dumps(body).encode()
        req=urllib.request.Request(self._url(path),data=data,method='POST',headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req) as resp:return resp.status,json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            with exc:return exc.code,json.loads(exc.read())

    def test_overview_returns_case_state_over_real_http(self):
        status,body=self._get(f'/api/cases/{self.case_id}')
        self.assertEqual(status,200)
        self.assertEqual(body['case_id'],self.case_id)

    def test_case_list_returns_event_cards_for_existing_cases(self):
        status,body=self._get('/api/cases')
        self.assertEqual(status,200)
        self.assertTrue(any(item['case_id']==self.case_id for item in body))
        self.assertTrue(all(item['title'] for item in body))

    def test_start_and_run_endpoints_create_and_continue_replay_case(self):
        status,started=self._post('/api/cases/start',dict(mode='replay',goal=GOAL,run=False))
        self.assertEqual(status,200)
        self.assertTrue(started['created'])
        new_case_id=started['case_id']
        status,result=self._post(f'/api/cases/{new_case_id}/run',dict(budget=dict(
            max_model_calls=36,max_tool_calls=70,max_delegations=5,max_seconds=180,
            max_request_tokens=16000,max_output_tokens=2400)))
        self.assertEqual(status,200)
        self.assertIn(result['outcome']['status'],('waiting_for_input','needs_review','investigation_complete'),
            (result, [e for e in self.server.case_store.audit_events(new_case_id)
                      if e['event_type'] in ('model_error','tool_result')][-5:]))

    def test_unknown_case_is_404(self):
        status,body=self._get('/api/cases/CASE-does-not-exist')
        self.assertEqual(status,404)

    def test_unknown_route_is_404(self):
        status,body=self._get('/api/does-not-exist')
        self.assertEqual(status,404)

    def test_queue_and_resolve_round_trip_over_real_http(self):
        status,queue=self._get(f'/api/cases/{self.case_id}/queue')
        self.assertEqual(status,200)
        fact=next(i for i in queue if i['section']=='fact')
        status,result=self._post(f"/api/cases/{self.case_id}/queue/{fact['id']}/resolve",ANSWER)
        self.assertEqual(status,200)
        self.assertEqual(result['kind'],'answer_question')

    def test_malformed_json_body_is_400(self):
        req=urllib.request.Request(self._url(f'/api/cases/{self.case_id}/queue/fact:x/resolve'),
            data=b'not json',method='POST',headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as ctx:urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code,400)

    def test_submit_evidence_over_real_http_then_appears_in_evidence_view(self):
        _,queue=self._get(f'/api/cases/{self.case_id}/queue')
        response=next(i for i in queue if i['section']=='response')
        self._post(f"/api/cases/{self.case_id}/queue/{response['id']}/resolve",dict(accepted_by_role_id=response['who']))
        content=(DEMO/'control_design.synthetic.txt').read_bytes()
        body=dict(action_key=response['key'],evidence_slot='design',evidence_type='control_design',
            submitted_by_role_id=response['who'],filename='design.txt',content_base64=base64.b64encode(content).decode())
        status,result=self._post(f'/api/cases/{self.case_id}/evidence',body)
        self.assertEqual(status,200)
        self.assertEqual(result['kind'],'submit_evidence')
        status,ev=self._get(f'/api/cases/{self.case_id}/evidence')
        self.assertTrue(any(e['evidence_key']=='design' for e in ev['current']))

    def test_submit_evidence_rejects_undeclared_slot_as_a_400(self):
        _,queue=self._get(f'/api/cases/{self.case_id}/queue')
        response=next(i for i in queue if i['section']=='response')
        self._post(f"/api/cases/{self.case_id}/queue/{response['id']}/resolve",dict(accepted_by_role_id=response['who']))
        content=(DEMO/'unrelated_policy.synthetic.txt').read_bytes()
        body=dict(action_key=response['key'],evidence_slot='not-a-real-slot',evidence_type='control_design',
            submitted_by_role_id=response['who'],filename='x.txt',content_base64=base64.b64encode(content).decode())
        status,result=self._post(f'/api/cases/{self.case_id}/evidence',body)
        self.assertEqual(status,400)


if __name__=='__main__':unittest.main(verbosity=2)
