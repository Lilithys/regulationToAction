"""M4: evidence submission, content review, human decisions, and action closure."""
import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from case_store import CaseStore
from source_intake import open_registered_case
from investigation_tools import InvestigationTools, PERMISSIONS
import evidence_intake
from run_case import GOAL

REQUIRED_EVIDENCE=[dict(evidence_key='design',evidence_type='control_design',title='Control design document'),
                   dict(evidence_key='test',evidence_type='control_effectiveness_test',title='Effectiveness test result')]


class BaseCase(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name,'cases.sqlite3')
        self.artifact_root=Path(self.tmp.name,'evidence_artifacts')
        self.store=CaseStore(self.path)
        self.case_id,_=open_registered_case(self.store,GOAL,'replay')
        self.service=InvestigationTools(self.store,self.case_id,'response_planner')
        costs=self.service.compare_costs()
        plan=self.service.propose_plan('OPT-ESG-AUTOMATED',['REQ-ESG-CREDIT-MONITORING-001'],'Credit monitoring phase',[costs['reference_id']])
        roles=self.service.find_roles('PROC-CREDIT-RISK-MONITORING')
        self.action=self.service.propose_action(plan['object_key'],'Stand up control','Steps','2026-12-31',
            'ROLE-CHIEF-RISK','note',REQUIRED_EVIDENCE,[roles['reference_id']])
        self.action_key=self.action['object_key']
        self.role='ROLE-CHIEF-RISK'

    def tearDown(self):self.store.close();self.tmp.cleanup()

    def accept(self):
        return self.store.accept_action(self.case_id,self.action_key,self.role,'accept-req',self.action['version'])

    def write_file(self,name,text):
        p=Path(self.tmp.name,name);p.write_text(text);return p

    def submit(self,slot,evidence_type,text='Synthetic test-only content.',filename=None):
        path=self.write_file(filename or slot+str(hash(text))+'.txt',text)
        return evidence_intake.submit_evidence(self.store,self.case_id,self.action_key,slot,evidence_type,path,self.artifact_root,self.role)

    def verify_both(self):
        design=self.submit('design','control_design')
        self.store.decide_evidence(self.case_id,design['object_key'],'verified',self.role,design['version'],'v-design')
        test=self.submit('test','control_effectiveness_test')
        self.store.decide_evidence(self.case_id,test['object_key'],'verified',self.role,test['version'],'v-test')


class SubmitEvidenceTests(BaseCase):
    def test_rejects_evidence_slot_not_declared_by_the_action(self):
        with self.assertRaises(ValueError):self.submit('fake-slot','control_design')

    def test_rejects_mismatched_evidence_type(self):
        with self.assertRaises(ValueError):self.submit('design','wrong_type')

    def test_rejects_missing_or_wrong_extension_file(self):
        bad=self.write_file('design.docx','not a real evidence format')
        with self.assertRaises(ValueError):
            evidence_intake.submit_evidence(self.store,self.case_id,self.action_key,'design','control_design',bad,self.artifact_root,self.role)

    def test_rejects_empty_file(self):
        empty=self.write_file('empty.txt','')
        with self.assertRaises(ValueError):
            evidence_intake.submit_evidence(self.store,self.case_id,self.action_key,'design','control_design',empty,self.artifact_root,self.role)

    def test_resubmitting_identical_content_while_pending_is_idempotent(self):
        first=self.submit('design','control_design',text='same content')
        second=self.submit('design','control_design',text='same content',filename='design_again.txt')
        self.assertEqual(first['object_id'],second['object_id'])

    def test_resubmitting_different_content_creates_new_version_and_resets_decision(self):
        first=self.submit('design','control_design',text='draft v1')
        self.store.decide_evidence(self.case_id,first['object_key'],'rejected',self.role,first['version'],'reject-1')
        second=self.submit('design','control_design',text='draft v2, materially different')
        self.assertGreater(second['version'],first['version'])
        self.assertIsNone(second['payload']['human_decision'])
        self.assertIsNone(second['payload']['content_assessment'])
        self.assertEqual(second['status'],'submitted')

    def test_stale_action_blocks_submission(self):
        self.store.put(self.case_id,'Action',self.action_key,self.action['payload'],self.action['depends_on'],'stale')
        with self.assertRaises(ValueError):self.submit('design','control_design')

    def test_submission_bumps_case_revision(self):
        before=self.store.case(self.case_id)['revision']
        self.submit('design','control_design')
        self.assertGreater(self.store.case(self.case_id)['revision'],before)


class ReadReviewEvidenceTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.evidence=self.submit('design','control_design',text='Automated ESG monitoring control design, v1.')
        self.bank=InvestigationTools(self.store,self.case_id,'bank_investigator')

    def test_read_evidence_returns_hash_verified_text_and_is_observed(self):
        result=self.bank.read_evidence(self.evidence['object_key'])
        self.assertEqual(result['status'],'ok')
        self.assertIn('ESG monitoring',result['text'])
        self.assertIn(result['reference_id'],self.bank.observed)

    def test_review_requires_the_evidence_actually_read_first(self):
        with self.assertRaises(ValueError):
            self.bank.review_evidence(self.evidence['object_key'],'plausibly_responsive','Looks fine',['FAKE-REF'])

    def test_review_rejects_citing_a_different_evidences_observation(self):
        other=self.submit('test','control_effectiveness_test')
        other_read=self.bank.read_evidence(other['object_key'])
        with self.assertRaises(ValueError):
            self.bank.review_evidence(self.evidence['object_key'],'plausibly_responsive','Wrong citation',[other_read['reference_id']])

    def test_review_persists_a_new_version_with_assessment_and_rationale(self):
        read=self.bank.read_evidence(self.evidence['object_key'])
        reviewed=self.bank.review_evidence(self.evidence['object_key'],'plausibly_responsive','Mentions the control by name',[read['reference_id']])
        self.assertGreater(reviewed['version'],self.evidence['version'])
        self.assertEqual(reviewed['payload']['content_assessment'],'plausibly_responsive')
        self.assertEqual(reviewed['payload']['assessed_by_role'],'bank_investigator')
        self.assertIsNone(reviewed['payload']['human_decision'])

    def test_cannot_review_evidence_that_is_already_decided(self):
        self.store.decide_evidence(self.case_id,self.evidence['object_key'],'verified',self.role,self.evidence['version'],'v1')
        read=self.bank.read_evidence(self.evidence['object_key'])
        with self.assertRaises(ValueError):
            self.bank.review_evidence(self.evidence['object_key'],'plausibly_responsive','late review',[read['reference_id']])


class DecideEvidenceTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.evidence=self.submit('design','control_design')

    def test_not_reachable_through_investigation_tools_or_any_role_permission(self):
        self.assertFalse(hasattr(InvestigationTools,'decide_evidence'))
        self.assertNotIn('decide_evidence',{name for names in PERMISSIONS.values() for name in names})

    def test_decision_must_be_verified_or_rejected(self):
        with self.assertRaises(ValueError):
            self.store.decide_evidence(self.case_id,self.evidence['object_key'],'approved',self.role,self.evidence['version'],'bad-decision')

    def test_wrong_version_is_rejected(self):
        with self.assertRaises(ValueError):
            self.store.decide_evidence(self.case_id,self.evidence['object_key'],'verified',self.role,self.evidence['version']+1,'k')

    def test_cannot_decide_an_already_decided_item_without_resubmission(self):
        self.store.decide_evidence(self.case_id,self.evidence['object_key'],'verified',self.role,self.evidence['version'],'first')
        with self.assertRaises(ValueError):
            self.store.decide_evidence(self.case_id,self.evidence['object_key'],'rejected',self.role,self.evidence['version'],'second')

    def test_idempotent_on_same_request_key(self):
        first=self.store.decide_evidence(self.case_id,self.evidence['object_key'],'verified',self.role,self.evidence['version'],'shared')
        again=self.store.decide_evidence(self.case_id,self.evidence['object_key'],'verified',self.role,self.evidence['version'],'shared')
        self.assertEqual(first,again)

    def test_reused_key_with_different_decision_is_rejected(self):
        self.store.decide_evidence(self.case_id,self.evidence['object_key'],'verified',self.role,self.evidence['version'],'shared')
        with self.assertRaises(ValueError):
            self.store.decide_evidence(self.case_id,self.evidence['object_key'],'rejected',self.role,self.evidence['version'],'shared')

    def test_rejection_does_not_delete_history(self):
        self.store.decide_evidence(self.case_id,self.evidence['object_key'],'rejected',self.role,self.evidence['version'],'reject')
        self.assertEqual(len(self.store.objects(self.case_id,'Evidence',current=False)),2)


class CheckClosureTests(BaseCase):
    def test_nothing_submitted_blocks_closure(self):
        gate=evidence_intake.evaluate_closure(self.store,self.case_id,self.action_key,self.artifact_root)
        self.assertFalse(gate['can_close'])
        self.assertTrue(any('missing evidence record' in r for r in gate['reasons']))

    def test_action_not_accepted_blocks_closure(self):
        self.verify_both()
        gate=evidence_intake.evaluate_closure(self.store,self.case_id,self.action_key,self.artifact_root)
        self.assertFalse(gate['can_close'])
        self.assertTrue(any('approval metadata' in r for r in gate['reasons']))

    def test_submitted_but_undecided_evidence_blocks_closure(self):
        self.accept()
        self.submit('design','control_design')
        self.submit('test','control_effectiveness_test')
        gate=evidence_intake.evaluate_closure(self.store,self.case_id,self.action_key,self.artifact_root)
        self.assertFalse(gate['can_close'])
        self.assertTrue(any('human review is incomplete' in r for r in gate['reasons']))

    def test_only_one_of_two_required_items_verified_blocks_closure(self):
        self.accept()
        design=self.submit('design','control_design')
        self.store.decide_evidence(self.case_id,design['object_key'],'verified',self.role,design['version'],'v-design')
        gate=evidence_intake.evaluate_closure(self.store,self.case_id,self.action_key,self.artifact_root)
        self.assertFalse(gate['can_close'])
        self.assertTrue(any('test' in r for r in gate['reasons']))

    def test_rejected_evidence_blocks_closure_even_if_a_file_exists(self):
        self.accept()
        design=self.submit('design','control_design')
        self.store.decide_evidence(self.case_id,design['object_key'],'rejected',self.role,design['version'],'reject')
        test=self.submit('test','control_effectiveness_test')
        self.store.decide_evidence(self.case_id,test['object_key'],'verified',self.role,test['version'],'v-test')
        gate=evidence_intake.evaluate_closure(self.store,self.case_id,self.action_key,self.artifact_root)
        self.assertFalse(gate['can_close'])

    def test_tampered_artifact_blocks_closure(self):
        self.accept()
        self.verify_both()
        for f in self.artifact_root.iterdir():f.write_text('tampered content, hash will no longer match')
        gate=evidence_intake.evaluate_closure(self.store,self.case_id,self.action_key,self.artifact_root)
        self.assertFalse(gate['can_close'])
        self.assertTrue(any('hash mismatch' in r for r in gate['reasons']))

    def test_fully_verified_evidence_allows_closure(self):
        self.accept()
        self.verify_both()
        gate=evidence_intake.evaluate_closure(self.store,self.case_id,self.action_key,self.artifact_root)
        self.assertTrue(gate['can_close'])
        self.assertEqual(gate['reasons'],[])

    def test_check_closure_tool_is_available_to_every_role(self):
        for role in PERMISSIONS:
            self.assertIn('check_closure',PERMISSIONS[role])


class CloseActionTests(BaseCase):
    def test_not_reachable_through_investigation_tools_or_any_role_permission(self):
        self.assertFalse(hasattr(InvestigationTools,'close_action'))
        self.assertNotIn('close_action',{name for names in PERMISSIONS.values() for name in names})

    def test_wrong_action_version_is_rejected(self):
        self.accept()
        current=self.store.get(self.case_id,'Action',self.action_key)
        with self.assertRaises(ValueError):
            self.store.close_action(self.case_id,self.action_key,self.role,current['version']+1,'close-wrong-version',self.artifact_root)

    def test_refuses_when_evidence_gate_is_not_satisfied(self):
        self.accept()
        current=self.store.get(self.case_id,'Action',self.action_key)
        with self.assertRaises(ValueError):
            self.store.close_action(self.case_id,self.action_key,self.role,current['version'],'close-no-evidence',self.artifact_root)

    def test_requires_accepted_status(self):
        self.verify_both()
        with self.assertRaises(ValueError):
            self.store.close_action(self.case_id,self.action_key,self.role,self.action['version'],'close-unaccepted',self.artifact_root)

    def test_closes_when_gate_passes_and_records_scope_disclaimer(self):
        self.accept()
        self.verify_both()
        current=self.store.get(self.case_id,'Action',self.action_key)
        result=self.store.close_action(self.case_id,self.action_key,self.role,current['version'],'close-ok',self.artifact_root)
        self.assertEqual(result['status'],'verified')
        closed=self.store.get(self.case_id,'Action',self.action_key)
        self.assertEqual(closed['status'],'verified')
        self.assertIn('not an approval of the full ESG requirement',closed['payload']['closure_scope_note'])

    def test_idempotent_on_same_request_key(self):
        self.accept()
        self.verify_both()
        current=self.store.get(self.case_id,'Action',self.action_key)
        first=self.store.close_action(self.case_id,self.action_key,self.role,current['version'],'shared-close',self.artifact_root)
        again=self.store.close_action(self.case_id,self.action_key,self.role,current['version'],'shared-close',self.artifact_root)
        self.assertEqual(first,again)

    def test_verified_action_becomes_stale_if_evidence_is_later_rejected(self):
        self.accept()
        self.verify_both()
        current=self.store.get(self.case_id,'Action',self.action_key)
        self.store.close_action(self.case_id,self.action_key,self.role,current['version'],'close-ok',self.artifact_root)
        self.assertEqual(self.store.get(self.case_id,'Action',self.action_key)['status'],'verified')
        design=self.submit('design','control_design',text='corrected design, re-submitted after closure')
        self.store.decide_evidence(self.case_id,design['object_key'],'rejected',self.role,design['version'],'reopen')
        self.assertEqual(self.store.get(self.case_id,'Action',self.action_key)['status'],'stale')


if __name__=='__main__':unittest.main(verbosity=2)
