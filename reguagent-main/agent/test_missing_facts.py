"""Confirms the documented dataset shape (no borrower has a second loan record)
empirically, and that unregistered facts stay unresolved rather than getting a
guessed answer."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from dataset_runtime import load_runtime
from missing_facts import attempt_infer_from_related_records, find_related_records, resolve_missing_fact


class MissingFactsTests(unittest.TestCase):
    def setUp(self):
        self.files = load_runtime()
        self.sme = [r for r in self.files['03_exposure/lending_portfolio.csv'] if r['borrower_type'] == 'sme']

    def test_no_sme_borrower_has_a_second_loan_record(self):
        # empirical check of logic A-B-C/B-Logic.md's documented finding
        for record in self.sme:
            self.assertEqual(find_related_records(self.sme, record), [])

    def test_inference_reports_no_related_records_for_this_dataset(self):
        result = attempt_infer_from_related_records('transition_risk', [])
        self.assertEqual(result['status'], 'no_related_records')

    def test_esg_energy_coverage_has_a_fixture_answer(self):
        entry = resolve_missing_fact('FACT-ESG-ENERGY-COVERAGE')
        self.assertEqual(entry['simulated_answer'], 65)

    def test_frtb_and_ips_facts_stay_unresolved_not_guessed(self):
        # matches CASE-IPS-BASE's expected unresolved_scope -- these must NOT get an answer
        for fact_id in ('FACT-FRTB-CURRENT-EXPOSURE', 'FACT-IPS-OTHER-CHANNELS'):
            with self.assertRaises(KeyError):
                resolve_missing_fact(fact_id)

    def test_all_three_registered_missing_facts_exist_in_the_dataset(self):
        registered = {f['fact_id'] for f in self.files['03_exposure/missing_facts.json']}
        self.assertEqual(registered, {'FACT-ESG-ENERGY-COVERAGE', 'FACT-FRTB-CURRENT-EXPOSURE', 'FACT-IPS-OTHER-CHANNELS'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
