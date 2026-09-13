#!/usr/bin/env python3
"""Offline deterministic development checks; not LLM end-to-end evaluation.

Current assertions cover available scenario facts, arithmetic and boundaries.
Two unimplemented auxiliary behaviours are explicit skips. AHP approval is not
required, and fixture availability is not reported as an executed interview.
"""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))                # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agent'))  # agent/

from dataset_runtime import APPROVED_DIRS, calculate_options, load_runtime, portfolio_metrics
from applicability import assess_requirement_applicability, direct_only_products, gate3_temporal_status
from evidence_closure import check_closure
from exposure_esg import CONFIDENCE_DIMENSIONS, EXPOSURE_DIMENSIONS, compute_portfolio_exposure
from gap_assessment import assess_capability_gap, frtb_restraint_check
from missing_facts import resolve_missing_fact
from exposure_esg import portfolio_fact_report


def find_requirement(files, requirement_id):
    return next(r for r in files['regulatory_sources/requirements.json']['requirements']
                if r['requirement_id'] == requirement_id)


class EvalGroundTruthCases(unittest.TestCase):
    def setUp(self):
        self.files = load_runtime()
        self.as_of = date(2026, 9, 8)
        self.controls_by_id = {c['control_id']: c for c in self.files['04_governance/controls.json']['controls']}

    def test_case_esg_base(self):
        req = find_requirement(self.files, 'REQ-ESG-CREDIT-MONITORING-001')
        applicability = assess_requirement_applicability(
            req, self.files['01_entity/bank_profile.json'], self.files['02_business/products.json'], self.as_of)
        self.assertIn(applicability['applicability'], ('direct', 'indirect'))  # expected.applicability

        facts = portfolio_fact_report(self.files, direct_only_products(applicability), self.as_of)
        self.assertEqual(facts['borrower_count'], 10000)
        self.assertEqual(facts['exposure_eur_millions'], 2300)
        self.assertAlmostEqual(facts['imprecise_sector_exposure_pct'], 910/2300*100)
        self.assertTrue(all(r['risk_assessment_status'] == 'unverified' for r in facts['groups']))
        self.assertTrue(all(r['unresolved_facts'] for r in facts['groups']))
        # Question availability is not an executed interview; E2E interaction remains T16/T24.
        missing = self.files['03_exposure/missing_facts.json']
        self.assertTrue(any(r['fact_id'] == 'FACT-ESG-ENERGY-COVERAGE' and r['value'] is None for r in missing))

    def test_case_ips_base_testable_parts(self):
        req = find_requirement(self.files, 'REQ-IPS-VOP-001')
        gap = assess_capability_gap(req, self.controls_by_id)
        self.assertIn('mobile', gap['rationale'])  # expected.known_gap = mobile_instant_payment_vop
        status, _event = gate3_temporal_status(req, self.files['01_entity/bank_profile.json'], self.as_of)
        self.assertEqual(status, 'in_force')  # expected.deadline_status = past_due (2025-10-09 has passed)
        with self.assertRaises(KeyError):
            resolve_missing_fact('FACT-IPS-OTHER-CHANNELS')  # stays genuinely unresolved, not answered

    @unittest.skip('PENDING: expected.unresolved_scope=[standard_sct, api] needs per-channel '
                   'applicability; applicability.py currently treats all 3 payment products '
                   'uniformly as direct -- the channel split only lives in the missing_facts '
                   'fixture today, not a real applicability determination. New code required.')
    def test_case_ips_base_channel_scope_PENDING(self):
        pass

    def test_case_dora_base_testable_parts(self):
        req = find_requirement(self.files, 'REQ-DORA-DEPENDENCY-MAP-001')
        gap = assess_capability_gap(req, self.controls_by_id)
        self.assertNotEqual(gap['status'], 'evidenced')  # must_not: assert_all_dora_compliance
        self.assertIn('third_party_dependency_mapping', gap['rationale'])

    @unittest.skip('PENDING: expected.confirmed_synthetic_gap_vendors names specific vendor IDs '
                   '(VND-CLOUD-INFRA, VND-MORTGAGE-SERVICER); gap_assessment.py reads control-level '
                   'coverage[], not vendors.json subcontractor status -- new code required.')
    def test_case_dora_base_vendor_specific_naming_PENDING(self):
        pass

    def test_case_frtb_base(self):
        result = frtb_restraint_check(self.files['01_entity/bank_profile.json'], self.files['02_business/business_lines.json'])
        self.assertIsNotNone(result)
        self.assertEqual(result['business_relevance'], 'limited')
        self.assertEqual(result['applicability'], 'uncertain')
        self.assertEqual(result['allowed_action'], 'refresh_scope_evidence_and_monitor')
        self.assertNotEqual(result['applicability'], 'not_applicable')  # must_not: blanket_market_risk_exemption
        # must_not: invent_frtb_remediation_programme -- this function never creates an action/response record at all

    def test_case_nace_weight(self):
        m = portfolio_metrics(self.files)
        self.assertEqual(m['missing_or_broad_nace_borrower_pct'], 20.0)
        self.assertAlmostEqual(m['missing_or_broad_nace_exposure_pct'], 39.56521739130435, places=8)

    def test_case_payment_sample(self):
        m = portfolio_metrics(self.files)
        self.assertAlmostEqual(m['observed_mobile_share_pct'], 75.1052483861914, places=6)
        self.assertFalse(m['payments_population_complete'])  # expected.can_extrapolate_sample = False

    def test_case_evidence_required(self):
        action = dict(action_id='ACT-TEST', required_evidence_ids=['EVD-TEST'],
                      human_review_status='approved', reviewed_by='r', reviewed_at='2026-09-08')
        evidence = [dict(evidence_id='EVD-TEST', action_id='ACT-TEST', status='required')]
        self.assertFalse(check_closure(action, evidence)['can_close'])

    def test_case_evidence_hash(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'fixture.txt').write_text('synthetic test-only artefact')
            action = dict(action_id='ACT-TEST', required_evidence_ids=['EVD-TEST'],
                          human_review_status='approved', reviewed_by='r', reviewed_at='2026-09-08')
            evidence = [dict(evidence_id='EVD-TEST', action_id='ACT-TEST', status='collected',
                             collected_at='2026-09-08', artifact_path='fixture.txt', content_sha256='0' * 64,
                             human_review_status='approved', reviewed_by='r', reviewed_at='2026-09-08')]
            self.assertFalse(check_closure(action, evidence, root=d)['can_close'])  # wrong hash

    def test_case_capacity_unknown(self):
        result = calculate_options(self.files)
        self.assertEqual(result['lowest_base_tco_option_id'], 'OPT-ESG-AUTOMATED')
        self.assertIsNone(result['recommended_option_id'])
        automated = next(o for o in result['options'] if o['option_id'] == 'OPT-ESG-AUTOMATED')
        self.assertIsNone(automated['capacity_sufficient'])

    def test_case_risk_cost_unknown(self):
        for option in calculate_options(self.files)['options']:
            self.assertIsNone(option['expected_risk_cost_eur'])  # must_not: treat_unknown_as_zero

    def test_case_peer_separation(self):
        self.assertNotIn('reference_only', APPROVED_DIRS)  # expected.peer_is_enterprise_evidence = False
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'dataset_manifest.json').write_text(json.dumps(
                {'operational_files': ['reference_only/bunq_reference_registry.json']}))
            with self.assertRaises(ValueError):
                load_runtime(d)

    def test_case_version_pair(self):
        esg_pair = next(p for p in self.files['regulatory_sources/version_pairs.json'] if p['topic'] == 'esg_risk')
        self.assertEqual(esg_pair['diff_status'], 'not_computed')  # expected.expected_status = insufficient_source_snapshots
        self.assertIsNone(esg_pair['older']['local_artifact'])     # must_not: invent_old_text
        self.assertIsNone(esg_pair['newer']['local_artifact'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
