"""Tests confirm_and_weigh()'s write-then-reuse cycle with draft_pairwise_matrix/
run_review_session mocked out (no real LLM call, no real input() needed) -- this is
exactly the code path that broke twice in manual runs (a stale 'registry'/'key'
reference left over from extracting load_confirmed_weights). Runs against a real
temp file, not an in-memory stub, to catch read/write bugs for real."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from exposure_esg import EXPOSURE_DIMENSIONS
import review_matrix_cli as rmc

CONTEXT = dict(requirement_id='REQ-TEST', requirement_text='Synthetic test requirement: monitor ESG risks.',
               source_citations=[{'citation_id':'TEST-CIT', 'evidence_text':'test fixture only'}],
               dataset_version='test-v1', scope_version='test-scope-v1')
FAKE_DRAFT = dict(requirement_id='REQ-TEST', dimension_set='exposure', dimension_names=EXPOSURE_DIMENSIONS,
    status='draft', drafted_by='test_fixture', pairs=[
        dict(dimension_a=EXPOSURE_DIMENSIONS[0], dimension_b=EXPOSURE_DIMENSIONS[1], ratio=2, reasoning='test fixture'),
        dict(dimension_a=EXPOSURE_DIMENSIONS[0], dimension_b=EXPOSURE_DIMENSIONS[2], ratio=4, reasoning='test fixture'),
        dict(dimension_a=EXPOSURE_DIMENSIONS[1], dimension_b=EXPOSURE_DIMENSIONS[2], ratio=2, reasoning='test fixture')])


class ConfirmAndWeighTests(unittest.TestCase):
    def test_write_then_reuse_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            registry_path = Path(d, 'pairwise_matrix_registry.json')
            with patch.object(rmc, 'draft_pairwise_matrix', return_value=copy.deepcopy(FAKE_DRAFT)), \
                 patch('builtins.input', return_value='y'):
                weights, cr, confirmed = rmc.confirm_and_weigh(
                    'REQ-TEST', 'exposure', EXPOSURE_DIMENSIONS, 'demo_reviewer', registry_path, requirement_context=CONTEXT)
            self.assertLess(cr, 0.10)
            self.assertAlmostEqual(sum(weights.values()), 1.0, places=6)
            self.assertTrue(registry_path.exists())

            # second call must reuse what was just written -- no draft/input this time,
            # and patching them to raise proves reuse actually happened, not luck.
            with patch.object(rmc, 'draft_pairwise_matrix', side_effect=AssertionError('should not redraft')), \
                 patch('builtins.input', side_effect=AssertionError('should not prompt')):
                weights2, cr2, _ = rmc.confirm_and_weigh(
                    'REQ-TEST', 'exposure', EXPOSURE_DIMENSIONS, 'demo_reviewer', registry_path, requirement_context=CONTEXT)
            self.assertEqual(weights, weights2)
            self.assertEqual(cr, cr2)

    def test_adjust_path_overrides_a_ratio(self):
        with tempfile.TemporaryDirectory() as d:
            registry_path = Path(d, 'pairwise_matrix_registry.json')
            inputs = iter(['adjust', '3', '', '', 'y'])  # override first pair to 9, keep the rest
            with patch.object(rmc, 'draft_pairwise_matrix', return_value=copy.deepcopy(FAKE_DRAFT)), \
                 patch('builtins.input', lambda *a: next(inputs)):
                _weights, _cr, confirmed = rmc.confirm_and_weigh(
                    'REQ-TEST', 'exposure', EXPOSURE_DIMENSIONS, 'demo_reviewer', registry_path, requirement_context=CONTEXT)
            self.assertEqual(confirmed['pairs'][0]['ratio'], 3.0)
            self.assertEqual(confirmed['pairs'][0]['original_ratio'], 2)
            self.assertEqual(confirmed['pairs'][0]['adjusted_by'], 'demo_reviewer')


if __name__ == '__main__':
    unittest.main(verbosity=2)
