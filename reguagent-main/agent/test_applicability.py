"""Runs Part A against real calibrated_v0_2 data -- not mocks. Mirrors the style
of scripts/test_dataset_runtime.py."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from dataset_runtime import load_runtime
from applicability import assess_requirement_applicability, gate3_temporal_status, resolve_pointer


def find_requirement(files, requirement_id):
    reqs = files['regulatory_sources/requirements.json']['requirements']
    return next(r for r in reqs if r['requirement_id'] == requirement_id)


class ApplicabilityTests(unittest.TestCase):
    def setUp(self):
        self.files = load_runtime()
        self.bank_profile = self.files['01_entity/bank_profile.json']
        self.products = self.files['02_business/products.json']
        self.as_of = date(2026, 9, 8)

    def test_resolve_pointer(self):
        value, found = resolve_pointer(self.bank_profile, '#/entity_classification')
        self.assertTrue(found)
        self.assertEqual(value, 'credit_institution')
        _, found = resolve_pointer(self.bank_profile, '#/not_a_real_field')
        self.assertFalse(found)

    def test_esg_credit_monitoring_direct_for_sme_loan(self):
        req = find_requirement(self.files, 'REQ-ESG-CREDIT-MONITORING-001')
        result = assess_requirement_applicability(req, self.bank_profile, self.products, self.as_of)
        self.assertEqual(result['applicability'], 'direct')
        self.assertIn('PRD-SME-WORKING-CAPITAL', result['in_scope_products'])

    def test_liquidity_product_is_limited_not_direct(self):
        req = find_requirement(self.files, 'REQ-ESG-CREDIT-MONITORING-001')
        result = assess_requirement_applicability(req, self.bank_profile, self.products, self.as_of)
        liquidity = next(r for r in result['product_results'] if r['product_id'] == 'PRD-LIQUIDITY-PORTFOLIO')
        self.assertEqual(liquidity['applicability'], 'limited')

    def test_mortgage_and_consumer_credit_are_indirect(self):
        req = find_requirement(self.files, 'REQ-ESG-CREDIT-MONITORING-001')
        result = assess_requirement_applicability(req, self.bank_profile, self.products, self.as_of)
        by_id = {r['product_id']: r['applicability'] for r in result['product_results']}
        self.assertEqual(by_id['PRD-RESIDENTIAL-MORTGAGE'], 'indirect')
        self.assertEqual(by_id['PRD-CONSUMER-LOAN'], 'indirect')
        self.assertEqual(by_id['PRD-GREEN-HOME-LOAN'], 'indirect')

    def test_esg_requirement_is_currently_in_force_non_snci(self):
        req = find_requirement(self.files, 'REQ-ESG-CREDIT-MONITORING-001')
        status, event = gate3_temporal_status(req, self.bank_profile, self.as_of)
        self.assertEqual(status, 'in_force')
        self.assertEqual(event['date'], '2026-01-11')

    def test_ips_institution_deadline_event_type_is_recognized(self):
        # requirements.json uses "institution_deadline" for IPS instead of ESG/DORA's
        # "application" -- gate3 must recognize both, or every IPS requirement falsely
        # reports an unknown temporal status.
        req = find_requirement(self.files, 'REQ-IPS-VOP-001')
        status, event = gate3_temporal_status(req, self.bank_profile, self.as_of)
        self.assertEqual(status, 'in_force')
        self.assertEqual(event['date'], '2025-10-09')

    def test_frtb_review_event_type_is_not_treated_as_a_binding_date(self):
        # REQ-FRTB-SMALL-BOOK-001's only compliance_event is event_type="review",
        # date=null (a recurring monitoring cadence, not a one-time application date)
        # -- must report unknown, not silently pick some other date.
        req = find_requirement(self.files, 'REQ-FRTB-SMALL-BOOK-001')
        status, event = gate3_temporal_status(req, self.bank_profile, self.as_of)
        self.assertEqual(status, 'unknown')
        self.assertIsNone(event)

    def test_frtb_transition_event_type_is_recognized(self):
        req = find_requirement(self.files, 'REQ-FRTB-APPLICATION-DATE-001')
        status, event = gate3_temporal_status(req, self.bank_profile, self.as_of)
        self.assertEqual(status, 'not_yet_effective')  # 2027-01-01, after as_of=2026-09-08
        self.assertEqual(event['date'], '2027-01-01')

    def test_snci_unknown_blocks_temporal_gate(self):
        req = find_requirement(self.files, 'REQ-ESG-CREDIT-MONITORING-001')
        bank_profile = dict(self.bank_profile, snci_status=None)
        status, _ = gate3_temporal_status(req, bank_profile, self.as_of)
        self.assertEqual(status, 'unknown')

    def test_requirement_review_status_is_carried_through(self):
        req = find_requirement(self.files, 'REQ-ESG-CREDIT-MONITORING-001')
        result = assess_requirement_applicability(req, self.bank_profile, self.products, self.as_of)
        sme_result = next(r for r in result['product_results'] if r['product_id'] == 'PRD-SME-WORKING-CAPITAL')
        self.assertEqual(sme_result['requirement_review_status'], 'silver')


if __name__ == '__main__':
    unittest.main(verbosity=2)
