"""M3: dynamic plan/action composition, RACI-grounded ownership, human-only acceptance."""
import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from case_store import CaseStore
from source_intake import open_registered_case
from investigation_tools import InvestigationTools, PERMISSIONS
from dataset_runtime import evaluate_option, deadline_status
from run_case import GOAL

REQUIRED_EVIDENCE=[dict(evidence_key='design',evidence_type='control_design',title='Control design document'),
                   dict(evidence_key='test',evidence_type='control_effectiveness_test',title='Effectiveness test result')]


class BaseCase(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name,'cases.sqlite3')
        self.store=CaseStore(self.path)
        self.case_id,_=open_registered_case(self.store,GOAL,'replay')
        self.service=InvestigationTools(self.store,self.case_id,'response_planner')
    def tearDown(self):self.store.close();self.tmp.cleanup()


class FindRolesTests(BaseCase):
    def test_known_process_returns_its_raci_accountable_candidate(self):
        result=self.service.find_roles('PROC-CREDIT-RISK-MONITORING')
        self.assertEqual([c['role_id'] for c in result['candidates']],['ROLE-CHIEF-RISK'])
        self.assertEqual(result['candidates'][0]['raci'],'A')
        self.assertIn('file:06_organisation/raci.csv',result['depends_on'])
        self.assertIn(result['reference_id'],self.service.observed)

    def test_unknown_process_id_is_rejected(self):
        with self.assertRaises(ValueError):self.service.find_roles('PROC-DOES-NOT-EXIST')

    def test_raci_row_with_unresolved_role_id_is_rejected(self):
        self.service.files['06_organisation/raci.csv'].append(
            dict(process_id='PROC-FAKE',role_id='ROLE-DOES-NOT-EXIST',raci='A',notes='fixture'))
        with self.assertRaises(ValueError):self.service.find_roles('PROC-FAKE')


class ProposePlanTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.costs=self.service.compare_costs()
        self.all_esg={r['requirement_id'] for r in self.service.files['regulatory_sources/requirements.json']['requirements']
                      if r['requirement_id'].startswith('REQ-ESG')}

    def test_plan_scoped_to_a_subset_matches_a_direct_evaluate_option_call(self):
        plan=self.service.propose_plan('OPT-ESG-AUTOMATED',['REQ-ESG-DATA-GAPS-001'],'Phase 1: data gaps only',[self.costs['reference_id']])
        template=next(o for o in self.service.files['07_economics/response_options.json'] if o['option_id']=='OPT-ESG-AUTOMATED')
        expected=evaluate_option(self.service.files,template,scope_requirement_ids=['REQ-ESG-DATA-GAPS-001'])
        self.assertEqual(plan['payload']['calculation'],expected)
        self.assertEqual(plan['payload']['addresses_requirement_ids'],['REQ-ESG-DATA-GAPS-001'])
        self.assertEqual(plan['payload']['deferred_requirement_ids'],sorted(self.all_esg-{'REQ-ESG-DATA-GAPS-001'}))
        self.assertEqual(plan['status'],'draft')
        self.assertEqual(plan['payload']['recommendation_status'],'needs_legal_review_and_delivery_team_capacity')

    def test_population_override_is_recorded_on_the_plan(self):
        plan=self.service.propose_plan('OPT-ESG-MANUAL',['REQ-ESG-DATA-GAPS-001','REQ-ESG-CREDIT-MONITORING-001'],
            'Full scope, half book piloted first',[self.costs['reference_id']],population_count=5000)
        self.assertEqual(plan['payload']['calculation']['population_basis'],'override')
        self.assertEqual(plan['payload']['calculation']['population_count'],5000)
        self.assertEqual(plan['payload']['deferred_requirement_ids'],sorted(self.all_esg-{'REQ-ESG-DATA-GAPS-001','REQ-ESG-CREDIT-MONITORING-001'}))

    def test_requirement_ids_must_be_subset_of_the_templates_own_scope(self):
        with self.assertRaises(ValueError):
            self.service.propose_plan('OPT-ESG-AUTOMATED',['REQ-ESG-RISK-APPETITE-001'],'Overclaim',[self.costs['reference_id']])

    def test_unknown_option_id_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.propose_plan('OPT-DOES-NOT-EXIST',['REQ-ESG-DATA-GAPS-001'],'Bad template',[self.costs['reference_id']])

    def test_reference_ids_must_have_been_actually_observed(self):
        with self.assertRaises(ValueError):
            self.service.propose_plan('OPT-ESG-AUTOMATED',['REQ-ESG-DATA-GAPS-001'],'Unobserved citation',['FAKE-REF-NOT-OBSERVED'])


class ProposeActionTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.costs=self.service.compare_costs()
        self.plan=self.service.propose_plan('OPT-ESG-AUTOMATED',['REQ-ESG-CREDIT-MONITORING-001'],
            'Credit monitoring phase',[self.costs['reference_id']])
        self.roles=self.service.find_roles('PROC-CREDIT-RISK-MONITORING')

    def test_action_grounds_owner_and_separates_regulatory_from_internal_dates(self):
        action=self.service.propose_action(self.plan['object_key'],'Stand up credit-monitoring control','Step 1...; Step 2...',
            '2026-12-31','ROLE-CHIEF-RISK','Depends on data-gaps phase closing first',REQUIRED_EVIDENCE,[self.roles['reference_id']])
        self.assertEqual(action['payload']['accountable_role_id'],'ROLE-CHIEF-RISK')
        self.assertEqual(action['payload']['acceptance_status'],'proposed')
        due=self.plan['payload']['calculation']['selected_regulatory_due_date']
        self.assertIsNotNone(due)
        self.assertEqual(action['payload']['regulatory_due_date'],due)
        self.assertEqual(action['payload']['regulatory_deadline_status'],deadline_status(due,self.service.case['as_of_date']))
        self.assertEqual(action['payload']['internal_target_status'],deadline_status('2026-12-31',self.service.case['as_of_date']))
        self.assertNotEqual(action['payload']['regulatory_due_date'],action['payload']['target_date'])

    def test_role_not_among_observed_candidates_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.propose_action(self.plan['object_key'],'Title','Steps','2026-12-31','ROLE-CIO','note',REQUIRED_EVIDENCE,[self.roles['reference_id']])

    def test_reference_ids_not_from_find_roles_do_not_ground_any_role(self):
        with self.assertRaises(ValueError):
            self.service.propose_action(self.plan['object_key'],'Title','Steps','2026-12-31','ROLE-CHIEF-RISK','note',REQUIRED_EVIDENCE,[self.costs['reference_id']])

    def test_unobserved_reference_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            self.service.propose_action(self.plan['object_key'],'Title','Steps','2026-12-31','ROLE-CHIEF-RISK','note',REQUIRED_EVIDENCE,['FAKE'])

    def test_action_requires_an_existing_non_stale_plan(self):
        with self.assertRaises(ValueError):
            self.service.propose_action('does-not-exist','Title','Steps','2026-12-31','ROLE-CHIEF-RISK','note',REQUIRED_EVIDENCE,[self.roles['reference_id']])
        self.store.put(self.case_id,'PlanVersion',self.plan['object_key'],self.plan['payload'],self.plan['depends_on'],'stale')
        with self.assertRaises(ValueError):
            self.service.propose_action(self.plan['object_key'],'Title','Steps','2026-12-31','ROLE-CHIEF-RISK','note',REQUIRED_EVIDENCE,[self.roles['reference_id']])

    def test_target_date_before_case_as_of_date_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.propose_action(self.plan['object_key'],'Title','Steps','2026-01-01','ROLE-CHIEF-RISK','note',REQUIRED_EVIDENCE,[self.roles['reference_id']])


class AcceptActionTests(BaseCase):
    def setUp(self):
        super().setUp()
        costs=self.service.compare_costs()
        plan=self.service.propose_plan('OPT-ESG-AUTOMATED',['REQ-ESG-CREDIT-MONITORING-001'],'Credit monitoring phase',[costs['reference_id']])
        roles=self.service.find_roles('PROC-CREDIT-RISK-MONITORING')
        self.action=self.service.propose_action(plan['object_key'],'Stand up control','Steps','2026-12-31','ROLE-CHIEF-RISK','note',REQUIRED_EVIDENCE,[roles['reference_id']])

    def test_not_reachable_through_investigation_tools_or_any_role_permission(self):
        self.assertFalse(hasattr(InvestigationTools,'accept_action'))
        self.assertNotIn('accept_action',{name for names in PERMISSIONS.values() for name in names})

    def test_accept_by_the_proposed_role_succeeds_and_is_idempotent(self):
        first=self.store.accept_action(self.case_id,self.action['object_key'],'ROLE-CHIEF-RISK','accept-1',self.action['version'])
        self.assertEqual(first['status'],'accepted')
        again=self.store.accept_action(self.case_id,self.action['object_key'],'ROLE-CHIEF-RISK','accept-1',self.action['version'])
        self.assertEqual(again,first)
        self.assertEqual(self.store.get(self.case_id,'Action',self.action['object_key'])['status'],'accepted')

    def test_wrong_role_cannot_accept(self):
        with self.assertRaises(ValueError):
            self.store.accept_action(self.case_id,self.action['object_key'],'ROLE-CIO','accept-wrong-role',self.action['version'])

    def test_wrong_version_is_rejected(self):
        with self.assertRaises(ValueError):
            self.store.accept_action(self.case_id,self.action['object_key'],'ROLE-CHIEF-RISK','accept-wrong-version',self.action['version']+1)

    def test_cannot_accept_twice_once_no_longer_draft(self):
        self.store.accept_action(self.case_id,self.action['object_key'],'ROLE-CHIEF-RISK','accept-first',self.action['version'])
        with self.assertRaises(ValueError):
            self.store.accept_action(self.case_id,self.action['object_key'],'ROLE-CHIEF-RISK','accept-second',self.action['version'])

    def test_idempotency_key_reused_with_different_acceptance_is_rejected(self):
        self.store.accept_action(self.case_id,self.action['object_key'],'ROLE-CHIEF-RISK','accept-shared',self.action['version'])
        with self.assertRaises(ValueError):
            self.store.accept_action(self.case_id,self.action['object_key'],'ROLE-CIO','accept-shared',self.action['version'])


if __name__=='__main__':unittest.main(verbosity=2)
