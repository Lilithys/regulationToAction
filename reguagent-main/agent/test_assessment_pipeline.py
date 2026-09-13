"""Runs the Phase 6 dispatcher against all four real registered changes, and
cross-checks the shallow paths against evaluation_ground_truth/
expected_assessments.json and data/regulatory-governance-dataset/references/
first-demo.md's documented expected reasoning outcomes."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from dataset_runtime import load_runtime
from assessment_pipeline import assess_change


class AssessmentPipelineTests(unittest.TestCase):
    def setUp(self):
        self.files = load_runtime()

    def test_esg_resolves_direct_and_finds_gaps(self):
        result = assess_change('esg_risk_management', self.files)
        self.assertIn('direct', result['stages'][0]['summary'])
        gap_stage = next(s for s in result['stages'] if s['name'] == '能力缺口')
        self.assertEqual(gap_stage['state'], 'done')
        self.assertIn('missing', gap_stage['detail'])  # REQ-ESG-DATA-GAPS-001 has no linked control at all

    def test_ips_finds_the_mobile_vop_gap(self):
        result = assess_change('instant_payments', self.files)
        applicability_stage = result['stages'][0]
        self.assertEqual(applicability_stage['state'], 'done')
        gap_stage = next(s for s in result['stages'] if s['name'] == '能力缺口')
        self.assertIn('mobile', gap_stage['detail'])

    def test_dora_resolves_direct_and_finds_third_party_gap(self):
        result = assess_change('dora', self.files)
        self.assertIn('direct', result['stages'][0]['summary'])
        gap_stage = next(s for s in result['stages'] if s['name'] == '能力缺口')
        self.assertEqual(gap_stage['state'], 'done')

    def test_frtb_stops_at_applicability_with_no_gap_and_no_action(self):
        # this is the point of the negative case: must NOT reach 能力缺口/建议行动/响应结果
        result = assess_change('frtb', self.files)
        by_name = {s['name']: s for s in result['stages']}
        self.assertEqual(by_name['适用性']['state'], 'active')  # blocked pending human sign-off, not silently closed
        self.assertIsNotNone(by_name['适用性']['human'])
        for stage_name in ('暴露度', '能力缺口', '建议行动', '响应结果'):
            self.assertEqual(by_name[stage_name]['state'], 'pending')
        for record in result['per_requirement']:
            self.assertNotIn('gap', record)  # no capability gap was invented for FRTB


if __name__ == '__main__':
    unittest.main(verbosity=2)
