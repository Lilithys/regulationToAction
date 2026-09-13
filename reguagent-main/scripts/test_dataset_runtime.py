"""Boundary and mutation checks, not model-accuracy claims."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from dataset_runtime import load_runtime, portfolio_metrics, calculate_options, closure_gate, deadline_status, evaluate_option


class DatasetRuntimeTests(unittest.TestCase):
    def setUp(self):self.files=load_runtime()

    def test_weighted_denominators(self):
        m=portfolio_metrics(self.files)
        self.assertEqual(m['missing_or_broad_nace_borrower_pct'],20)
        self.assertAlmostEqual(m['missing_or_broad_nace_exposure_pct'],910/2300*100)

    def test_portfolio_population_changes_cost(self):
        before=calculate_options(self.files)['options'][0]['scenarios']['base']['annual_run_cost_eur']
        for r in self.files['03_exposure/lending_portfolio.csv']:
            if r['borrower_type']=='sme':r['borrower_count']=str(int(r['borrower_count'])*2)
        self.assertEqual(calculate_options(self.files)['options'][0]['scenarios']['base']['annual_run_cost_eur'],before*2)

    def test_rate_change_propagates(self):
        before=calculate_options(self.files)['options'][0]
        next(r for r in self.files['07_economics/operational_costs.csv'] if r['cost_centre_id']=='CC-100')['unit_cost_eur']='832'
        after=calculate_options(self.files)['options'][0]
        self.assertEqual(after['setup_total_eur']-before['setup_total_eur'],8320)
        self.assertEqual(after['scenarios']['base']['annual_run_cost_eur'],520000)

    def test_automation_bounds(self):
        self.files['07_economics/response_options.json'][0]['automation_rate']=1.1
        with self.assertRaises(ValueError):calculate_options(self.files)

    def test_unknown_capacity_and_risk_are_not_zero(self):
        r=calculate_options(self.files)
        self.assertIsNone(r['recommended_option_id'])
        self.assertIsNone(r['options'][0]['capacity_sufficient'])
        self.assertIsNone(r['options'][0]['expected_risk_cost_eur'])

    def test_capacity_insufficient(self):
        self.files['07_economics/response_options.json'][0]['delivery_team_capacity_days']=1
        self.assertFalse(calculate_options(self.files)['options'][0]['capacity_sufficient'])

    def test_snci_date_changes_feasibility(self):
        self.assertFalse(calculate_options(self.files)['options'][0]['regulatory_deadline_feasible'])
        self.files['01_entity/bank_profile.json']['snci_status']=True
        self.assertTrue(calculate_options(self.files)['options'][0]['regulatory_deadline_feasible'])
        self.files['01_entity/bank_profile.json']['snci_status']=None
        self.assertIsNone(calculate_options(self.files)['options'][0]['regulatory_deadline_feasible'])

    def test_deadline_boundary(self):
        self.assertEqual(deadline_status('2026-09-08','2026-09-08'),'due_today')
        self.assertEqual(deadline_status('2026-09-07','2026-09-08'),'past_due')
        self.assertEqual(deadline_status(None,'2026-09-08'),'unknown')

    def test_input_profiles(self):
        mapping=json.dumps(load_runtime(profile='mapping'))
        self.assertNotIn('current_coverage',mapping)
        self.assertNotIn('gap_flags',mapping)
        self.assertNotIn('regulatory_sources/requirements.json',load_runtime(profile='extraction'))

    def test_manifest_cannot_include_answers(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,'dataset_manifest.json').write_text(json.dumps({'operational_files':['evaluation_ground_truth/reference_actions.json']}))
            with self.assertRaises(ValueError):load_runtime(d)

    def test_required_evidence_never_closes(self):
        a={'action_id':'ACT-TEST','required_evidence_ids':['EVD-TEST'],'human_review_status':'approved','reviewed_by':'fixture_reviewer','reviewed_at':'2026-09-08'}
        e={'evidence_id':'EVD-TEST','action_id':'ACT-TEST','status':'required'}
        self.assertFalse(closure_gate(a,[e])['can_close'])

    def test_hash_and_review_gate(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d,'fixture.txt');p.write_text('Synthetic test-only artefact; no actual approval.')
            a={'action_id':'ACT-TEST','required_evidence_ids':['EVD-TEST'],'human_review_status':'approved','reviewed_by':'simulated_test_reviewer','reviewed_at':'2026-09-08'}
            e={'evidence_id':'EVD-TEST','action_id':'ACT-TEST','status':'collected','human_review_status':'approved',
               'reviewed_by':'simulated_test_reviewer','reviewed_at':'2026-09-08','collected_at':'2026-09-08',
               'artifact_path':'fixture.txt','content_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            self.assertTrue(closure_gate(a,[e],d)['can_close'])
            e['content_sha256']='0'*64
            self.assertFalse(closure_gate(a,[e],d)['can_close'])
            e['content_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();e['reviewed_by']=None
            self.assertFalse(closure_gate(a,[e],d)['can_close'])


class ScopedOptionTests(unittest.TestCase):
    """T17: calculate_options() must stay the byte-for-byte regression baseline
    while evaluate_option() adds scope/population/budget as explicit parameters."""
    def setUp(self):
        self.files=load_runtime()
        self.options=self.files['07_economics/response_options.json']

    def test_calculate_options_numbers_are_unchanged_by_the_refactor(self):
        automated=next(o for o in calculate_options(self.files)['options'] if o['option_id']=='OPT-ESG-AUTOMATED')
        self.assertEqual(automated['scenarios']['base']['three_year_tco_eur'],451436.0)
        self.assertNotIn('budget_status',automated)

    def test_calculate_options_defaults_scope_to_each_templates_own_requirement_ids(self):
        for template,result in zip(self.options,calculate_options(self.files)['options']):
            self.assertEqual(result['addresses_requirement_ids'],template['requirement_ids'])
            self.assertEqual(result['population_basis'],'full_sme_book')

    def test_scope_override_is_recorded_not_the_templates_own(self):
        result=evaluate_option(self.files,self.options[0],scope_requirement_ids=['REQ-ESG-DATA-GAPS-001'])
        self.assertEqual(result['addresses_requirement_ids'],['REQ-ESG-DATA-GAPS-001'])
        self.assertNotEqual(result['addresses_requirement_ids'],self.options[0]['requirement_ids'])

    def test_population_override_scales_variable_cost_but_not_fixed_setup(self):
        # setup (people + technology/vendor/training/legal) is a fixed one-time
        # assumption in the template, independent of population -- a caller
        # composing a phased plan must not re-pay it per phase; only the
        # per-customer annual run cost should scale with a narrower population.
        full=evaluate_option(self.files,self.options[0],population_count=10000)
        half=evaluate_option(self.files,self.options[0],population_count=5000)
        self.assertEqual(half['setup_total_eur'],full['setup_total_eur'])
        self.assertAlmostEqual(half['scenarios']['base']['annual_manual_operating_cost_eur'],
                                full['scenarios']['base']['annual_manual_operating_cost_eur']/2,places=2)
        self.assertEqual(half['population_basis'],'override')

    def test_negative_population_is_rejected(self):
        with self.assertRaises(ValueError):evaluate_option(self.files,self.options[0],population_count=-1)

    def test_non_integer_population_is_rejected(self):
        with self.assertRaises(ValueError):evaluate_option(self.files,self.options[0],population_count=10000.5)

    def test_budget_flags_over_and_within(self):
        automated=next(o for o in self.options if o['option_id']=='OPT-ESG-AUTOMATED')
        tight=evaluate_option(self.files,automated,budget={'construction_budget_eur':90000})
        self.assertEqual(tight['budget_status'],'over_budget')
        self.assertGreater(tight['over_budget_eur'],0)
        self.assertEqual(tight['over_budget_eur'],round(tight['setup_total_eur']-90000,2))
        loose=evaluate_option(self.files,automated,budget={'construction_budget_eur':10_000_000})
        self.assertEqual(loose['budget_status'],'within_budget')
        self.assertEqual(loose['over_budget_eur'],0.0)

    def test_negative_budget_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_option(self.files,self.options[0],budget={'construction_budget_eur':-1})

    def test_no_budget_argument_means_no_budget_fields(self):
        result=evaluate_option(self.files,self.options[0])
        self.assertNotIn('budget_status',result);self.assertNotIn('over_budget_eur',result)

    def test_calculate_options_threads_budget_to_every_option(self):
        result=calculate_options(self.files,budget={'construction_budget_eur':90000})
        self.assertTrue(all('budget_status' in o for o in result['options']))
        manual=next(o for o in result['options'] if o['option_id']=='OPT-ESG-MANUAL')
        self.assertEqual(manual['budget_status'],'within_budget')  # manual setup is 26,818 EUR


if __name__=='__main__':unittest.main(verbosity=2)
