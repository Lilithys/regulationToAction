"""Scoring functions against real lending_portfolio.csv; AHP math against
constructed matrices (a clean one, and B-Logic.md's own documented contradictory
example: A>B by 5, B>C by 5, C>A by 5 must fail the consistency check)."""
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from dataset_runtime import load_runtime
from exposure_esg import (ahp_weights, band_of, compute_exposure_with_gaps, compute_portfolio_exposure,
                           matrix_from_pairs, score_data_debt, score_materiality, score_sector_concentration)

# Arithmetic fixtures, not human-approved or calibrated risk weights.
VALIDATED_EXPOSURE_WEIGHTS = dict(transition_risk=0.4, physical_risk=0.4, review_urgency=0.2)
VALIDATED_CONFIDENCE_WEIGHTS = dict(sector_classification=0.25, esg_data_availability=0.25,
                                   geography_coverage=0.25, assessment_freshness=0.25)


class ScoringAgainstRealPortfolioTests(unittest.TestCase):
    def setUp(self):
        files = load_runtime()
        self.sme = [r for r in files['03_exposure/lending_portfolio.csv'] if r['borrower_type'] == 'sme']
        self.book_total = sum(Decimal(r['outstanding_balance_eur_millions']) for r in self.sme)

    def test_max_sector_share_lands_in_75_band_not_100(self):
        # calibration_report.md: observed max sector share is ~19.57%, deliberately
        # below the raw 20% threshold -- confirms the banded version, not the raw rule.
        sector_total = {}
        for r in self.sme:
            sector_total[r['sector_name']] = sector_total.get(r['sector_name'], Decimal(0)) + Decimal(r['outstanding_balance_eur_millions'])
        max_share = float(max(sector_total.values()) / self.book_total)
        self.assertAlmostEqual(max_share, 0.1957, places=3)
        self.assertEqual(score_sector_concentration(max_share), 75)

    def test_materiality_uses_bands_not_deciles(self):
        largest = max(Decimal(r['outstanding_balance_eur_millions']) for r in self.sme)
        share = float(largest / self.book_total)
        expected = 100 if share >= 0.15 else 75 if share >= 0.10 else 50 if share >= 0.05 else 25
        self.assertEqual(score_materiality(float(largest), float(self.book_total)), expected)


class ExposureArithmeticTests(unittest.TestCase):
    def test_gap_range_widens_with_unresolved_dimensions(self):
        result = compute_exposure_with_gaps({'a': 100}, ['b'], {'a': 0.5, 'b': 0.5})
        self.assertIsNone(result['exposure_score'])
        self.assertEqual(result['exposure_range'], [60.0, 100.0])
        self.assertTrue(result['indeterminate'])

    def test_no_gaps_gives_a_point_score(self):
        result = compute_exposure_with_gaps({'a': 80, 'b': 40}, [], {'a': 0.5, 'b': 0.5})
        self.assertEqual(result['exposure_score'], 60.0)
        self.assertFalse(result['indeterminate'])

    def test_data_debt_uses_geometric_mean(self):
        # a plain product of three <=1 fractions collapses toward 0; geometric mean should not
        debt = score_data_debt(balance=100, book_total=1000, confidence_score=20, urgency_score=100)
        self.assertGreater(debt, 30)


class PortfolioExposureTests(unittest.TestCase):
    def setUp(self):
        self.files = load_runtime()
        from datetime import date
        self.as_of = date(2026, 9, 8)

    def test_priority_is_explicitly_synthetic_and_not_probability(self):
        # matches B-Logic.md's own worked example (PORT-SME-001/002 scoring ~85.5)
        # and CASE-ESG-BASE's expected exposure=high_candidate
        results = compute_portfolio_exposure(self.files, ['PRD-SME-WORKING-CAPITAL'],
                                              VALIDATED_EXPOSURE_WEIGHTS, VALIDATED_CONFIDENCE_WEIGHTS, self.as_of)
        self.assertTrue(all(r['risk_confidence'] is None for r in results))
        self.assertTrue(all(r['unresolved_facts'] for r in results))
        self.assertTrue(all('synthetic' in r['ranking_use'] for r in results))

    def test_records_with_unresolved_risk_band_get_a_range_not_a_guess(self):
        results = compute_portfolio_exposure(self.files, ['PRD-SME-WORKING-CAPITAL'],
                                              VALIDATED_EXPOSURE_WEIGHTS, VALIDATED_CONFIDENCE_WEIGHTS, self.as_of)
        indeterminate = [r for r in results if r['exposure_indeterminate']]
        self.assertTrue(indeterminate)
        for r in indeterminate:
            self.assertIsNone(r['exposure_score'])
            self.assertEqual(r['exposure_band'], 'indeterminate')
            self.assertTrue(r['unresolved_dimensions'])

    def test_no_in_scope_records_returns_empty_not_an_error(self):
        results = compute_portfolio_exposure(self.files, ['PRD-DOES-NOT-EXIST'],
                                              VALIDATED_EXPOSURE_WEIGHTS, VALIDATED_CONFIDENCE_WEIGHTS, self.as_of)
        self.assertEqual(results, [])

    def test_sector_proxy_dimensions_are_tagged_not_silently_treated_as_measured(self):
        # this is the whole point of the proxy design (CASE-ESG-BASE's
        # must_not: treat_proxy_as_measured_emissions) -- a record scored via the
        # sector proxy table must say so, not look identical to real band data.
        results = compute_portfolio_exposure(self.files, ['PRD-SME-WORKING-CAPITAL'],
                                              VALIDATED_EXPOSURE_WEIGHTS, VALIDATED_CONFIDENCE_WEIGHTS, self.as_of)
        proxied = [r for r in results if r['proxy_dimensions']]
        self.assertEqual(len(proxied), 8)  # every sector except PORT-SME-008's "sector_unclassified"
        for r in proxied:
            self.assertIn('transition_risk', r['proxy_dimensions'])
            self.assertIn('physical_risk', r['proxy_dimensions'])

    def test_unclassified_sector_still_falls_through_to_a_range(self):
        # PORT-SME-008: sector_name="sector_unclassified" isn't in the proxy table
        # either -- must stay genuinely unresolved, not silently default to a band.
        results = compute_portfolio_exposure(self.files, ['PRD-SME-WORKING-CAPITAL'],
                                              VALIDATED_EXPOSURE_WEIGHTS, VALIDATED_CONFIDENCE_WEIGHTS, self.as_of)
        record = next(r for r in results if 'PORT-SME-008' in r['source_record_ids'])
        self.assertTrue(record['exposure_indeterminate'])
        self.assertEqual(set(record['unresolved_dimensions']), {'transition_risk', 'physical_risk'})

    def test_bands(self):
        self.assertEqual(band_of(75), 'high')
        self.assertEqual(band_of(50), 'medium')
        self.assertEqual(band_of(10), 'low')
        self.assertEqual(band_of(None), 'indeterminate')


class AhpTests(unittest.TestCase):
    def test_consistent_matrix_produces_low_cr_and_ordered_weights(self):
        dims = ['a', 'b', 'c']
        pairs = [dict(dimension_a='a', dimension_b='b', ratio=2), dict(dimension_a='b', dimension_b='c', ratio=2), dict(dimension_a='a', dimension_b='c', ratio=4)]
        weights, cr = ahp_weights(matrix_from_pairs(pairs, dims), dims)
        self.assertLess(cr, 0.10)
        self.assertGreater(weights['a'], weights['b'])
        self.assertGreater(weights['b'], weights['c'])
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=6)

    def test_contradictory_matrix_is_rejected(self):
        # logic A-B-C/B-Logic.md's own documented example: A>B by 5, B>C by 5, but C>A by 5 too.
        dims = ['a', 'b', 'c']
        pairs = [dict(dimension_a='a', dimension_b='b', ratio=5),
                 dict(dimension_a='b', dimension_b='c', ratio=5),
                 dict(dimension_a='c', dimension_b='a', ratio=5)]
        with self.assertRaises(ValueError):
            ahp_weights(matrix_from_pairs(pairs, dims), dims)


if __name__ == '__main__':
    unittest.main(verbosity=2)
