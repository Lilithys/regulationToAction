"""Confirms the Phase 5 wrapper routes closure_gate()'s reasons into the right
queue section without reimplementing any of the gate logic itself."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from evidence_closure import check_closure


class EvidenceClosureTests(unittest.TestCase):
    def test_nothing_submitted_yet_routes_to_closure_section(self):
        action = dict(action_id='ACT-TEST', required_evidence_ids=['EVD-TEST'],
                      human_review_status='approved', reviewed_by='r', reviewed_at='2026-09-08')
        evidence = [dict(evidence_id='EVD-TEST', action_id='ACT-TEST', status='required')]
        result = check_closure(action, evidence)
        self.assertFalse(result['can_close'])
        self.assertEqual(result['queue_item']['section'], 'closure')
        self.assertEqual(result['queue_item']['payload']['actionTitle'], 'ACT-TEST')

    def test_submitted_but_unreviewed_routes_to_evidence_section(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d, 'fixture.txt')
            path.write_text('synthetic test-only artefact')
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            action = dict(action_id='ACT-TEST', required_evidence_ids=['EVD-TEST'],
                          human_review_status='approved', reviewed_by='r', reviewed_at='2026-09-08')
            evidence = [dict(evidence_id='EVD-TEST', action_id='ACT-TEST', status='collected',
                             collected_at='2026-09-08', artifact_path='fixture.txt', content_sha256=digest,
                             human_review_status=None, reviewed_by=None, reviewed_at=None)]
            result = check_closure(action, evidence, root=d)
            self.assertFalse(result['can_close'])
            self.assertEqual(result['queue_item']['section'], 'evidence')
            self.assertTrue(any('review' in r for r in result['queue_item']['payload']['items']))

    def test_fully_satisfied_closes_with_no_queue_item(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d, 'fixture.txt')
            path.write_text('synthetic test-only artefact')
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            action = dict(action_id='ACT-TEST', required_evidence_ids=['EVD-TEST'],
                          human_review_status='approved', reviewed_by='r', reviewed_at='2026-09-08')
            evidence = [dict(evidence_id='EVD-TEST', action_id='ACT-TEST', status='collected',
                             collected_at='2026-09-08', artifact_path='fixture.txt', content_sha256=digest,
                             human_review_status='approved', reviewed_by='r', reviewed_at='2026-09-08')]
            result = check_closure(action, evidence, root=d)
            self.assertTrue(result['can_close'])
            self.assertIsNone(result['queue_item'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
