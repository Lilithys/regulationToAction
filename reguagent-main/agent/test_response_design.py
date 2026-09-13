"""Runs Phase 4 against the real calculate_options() output and real roles.json --
confirms the wrapper doesn't reimplement the TCO math and honestly flags
multi-candidate cost centres instead of silently picking an owner."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from dataset_runtime import load_runtime
from response_design import compare_response_options, package_chosen_option, resolve_cost_centre_owners


class ResponseDesignTests(unittest.TestCase):
    def setUp(self):
        self.files = load_runtime()
        self.roles = self.files['06_organisation/roles.json']
        self.cc_names = {r['cost_centre_id']: r['cost_centre_name'] for r in self.files['07_economics/operational_costs.csv']}
        self.response_options = self.files['07_economics/response_options.json']

    def test_comparison_matches_dataset_runtime_directly(self):
        # not re-deriving the math here -- just confirming the wrapper is a passthrough
        from dataset_runtime import calculate_options
        direct = calculate_options(self.files)
        wrapped = compare_response_options(self.files)
        self.assertEqual(direct, wrapped)

    def test_cc_300_has_two_technology_candidates_not_guessed(self):
        # ROLE-CIO and ROLE-HEAD-DIGITAL both carry cost_centre_id CC-300 in this
        # dataset -- confirms owner resolution can't safely pick a single role even
        # for the "obvious" IT cost centre, so needs_human_assignment is the honest
        # answer, not an edge case.
        owners = resolve_cost_centre_owners({'CC-300': 90}, self.roles)
        self.assertEqual(sorted(owners['CC-300']), ['ROLE-CIO', 'ROLE-HEAD-DIGITAL'])

    def test_cc_200_has_multiple_candidates_and_is_flagged_not_guessed(self):
        owners = resolve_cost_centre_owners({'CC-200': 20}, self.roles)
        self.assertGreater(len(owners['CC-200']), 1)  # Risk is shared by several roles in this dataset

    def test_package_automated_option_flags_needs_human_assignment(self):
        comparison = compare_response_options(self.files)
        action = package_chosen_option(comparison, self.response_options, 'OPT-ESG-AUTOMATED',
                                        ['REQ-ESG-DATA-GAPS-001', 'REQ-ESG-CREDIT-MONITORING-001'],
                                        self.roles, self.cc_names, ['EVD-ESG-DATA-QUALITY-REPORT'],
                                        date(2026, 9, 8))
        self.assertEqual(action['owner_assignment_status'], 'needs_human_assignment')
        self.assertIn('ROLE-CIO', action['candidate_owners_by_cost_centre']['Data-IT'])
        self.assertGreater(action['estimated_total_cost_eur'], 0)
        self.assertIsNone(action['capacity_sufficient'])  # response_options.json's capacity field is null by design


if __name__ == '__main__':
    unittest.main(verbosity=2)
