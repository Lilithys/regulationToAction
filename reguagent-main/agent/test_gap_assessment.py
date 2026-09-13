"""Runs Part C gap logic against real calibrated_v0_2 data, cross-checked against
evaluation_ground_truth/expected_assessments.json's CASE-FRTB-BASE where applicable."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from dataset_runtime import load_runtime
from gap_assessment import assess_capability_gap, frtb_restraint_check


def find_requirement(files, requirement_id):
    reqs = files['regulatory_sources/requirements.json']['requirements']
    return next(r for r in reqs if r['requirement_id'] == requirement_id)


class GapAssessmentTests(unittest.TestCase):
    def setUp(self):
        self.files = load_runtime()
        self.controls_by_id = {c['control_id']: c for c in self.files['04_governance/controls.json']['controls']}
        self.bank_profile = self.files['01_entity/bank_profile.json']
        self.business_lines = self.files['02_business/business_lines.json']

    def test_no_linked_control_requires_investigation(self):
        req = find_requirement(self.files, 'REQ-ESG-DATA-GAPS-001')
        result = assess_capability_gap(req, self.controls_by_id)
        self.assertEqual(result['status'], 'insufficient_evidence')

    def test_origination_policy_gap_is_requirement_specific(self):
        req = find_requirement(self.files, 'REQ-ESG-CREDIT-POLICY-001')
        result = assess_capability_gap(req, self.controls_by_id)
        self.assertEqual(result['status'], 'partial')
        self.assertIn('esg_origination_criteria', result['rationale'])
        self.assertNotIn('existing_portfolio', result['rationale'])

    def test_vop_web_control_is_partial_mobile_gap(self):
        req = find_requirement(self.files, 'REQ-IPS-VOP-001')
        result = assess_capability_gap(req, self.controls_by_id)
        self.assertEqual(result['status'], 'partial')
        self.assertIn('mobile', result['rationale'])

    def test_dora_dependency_map_is_partial_third_party_gap(self):
        req = find_requirement(self.files, 'REQ-DORA-DEPENDENCY-MAP-001')
        result = assess_capability_gap(req, self.controls_by_id)
        self.assertEqual(result['status'], 'partial')
        self.assertIn('third_party_dependency_mapping', result['rationale'])

    def test_unresolvable_control_id_is_insufficient_evidence_not_missing(self):
        req = dict(requirement_id='REQ-FAKE', control_ids=['CTRL-DOES-NOT-EXIST'])
        result = assess_capability_gap(req, self.controls_by_id)
        self.assertEqual(result['status'], 'insufficient_evidence')

    def test_frtb_restraint_matches_eval_case_frtb_base(self):
        result = frtb_restraint_check(self.bank_profile, self.business_lines)
        self.assertIsNotNone(result)
        # Cross-checked against calibrated_v0_2/evaluation_ground_truth/expected_assessments.json
        self.assertEqual(result['business_relevance'], 'limited')
        self.assertEqual(result['applicability'], 'uncertain')
        self.assertEqual(result['allowed_action'], 'refresh_scope_evidence_and_monitor')
        self.assertEqual(result['queue_item']['section'], 'earlyexit')
        # must_not: applicability='uncertain' (not 'not_applicable'/'exempt') already
        # rules out CASE-FRTB-BASE's blanket_market_risk_exemption; no action/response
        # record is created here at all, which rules out invent_frtb_remediation_programme.
        self.assertNotEqual(result['applicability'], 'not_applicable')


if __name__ == '__main__':
    unittest.main(verbosity=2)
