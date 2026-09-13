"""Disposable demo bootstrap and replay-only API boundaries."""
import base64
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import serve_demo
from api_server import make_server
from case_store import CaseStore


class DemoBootstrapTests(unittest.TestCase):
    def test_initialization_preserves_existing_case_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cases.sqlite3'
            self.assertTrue(serve_demo.initialize_demo(path))
            with CaseStore(path) as store:
                cases = store.cases()
                self.assertEqual(len(cases), 2)
                for case in cases:
                    self.assertEqual(case['mode'], 'replay')
                    self.assertTrue(store.verify_audit(case['case_id']))
                original = [(c['case_id'], c['revision']) for c in cases]
            self.assertFalse(serve_demo.initialize_demo(path))
            with CaseStore(path) as store:
                self.assertEqual([(c['case_id'], c['revision']) for c in store.cases()], original)

    def test_failed_seed_does_not_leave_a_partial_demo(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cases.sqlite3'
            with patch.object(serve_demo, 'compressed_run', side_effect=RuntimeError('seed failed')):
                with self.assertRaisesRegex(RuntimeError, 'seed failed'):
                    serve_demo.initialize_demo(path)
            with CaseStore(path) as store:
                self.assertEqual(store.cases(), [])


class DemoApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'cases.sqlite3'
        serve_demo.initialize_demo(self.path)
        self.server = make_server(self.path, port=0, replay_only=True)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.worker.join()
        self.server.server_close()
        self.server.case_store.close()
        self.tmp.cleanup()

    def request(self, path, body=None):
        request = urllib.request.Request(self.base + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type': 'application/json'})
        try:
            response = urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_health_and_seeded_views_are_available(self):
        self.assertEqual(self.request('/api/health'), (200, {'status': 'ok', 'replay_only': True}))
        status, cases = self.request('/api/cases')
        self.assertEqual(status, 200)
        self.assertEqual(len(cases), 2)
        for case in cases:
            for suffix in ('', '/decision-view', '/investigation', '/plans', '/evidence', '/queue', '/audit'):
                self.assertEqual(self.request('/api/cases/' + case['case_id'] + suffix)[0], 200)

    def test_live_mode_is_blocked_before_any_model_call(self):
        with patch('api_server.client_for') as client:
            status, result = self.request('/api/cases/start', {'mode': 'live'})
        self.assertEqual(status, 403)
        self.assertIn('replay mode only', result['message'])
        client.assert_not_called()

    def test_upload_cannot_write_outside_temporary_upload_directory(self):
        _, cases = self.request('/api/cases')
        body = dict(action_key='example', evidence_slot='design', evidence_type='control_design',
            submitted_by_role_id='ROLE-CHIEF-RISK', filename='../escape.txt',
            content_base64=base64.b64encode(b'example').decode())
        status, result = self.request('/api/cases/' + cases[0]['case_id'] + '/evidence', body)
        self.assertEqual(status, 400)
        self.assertIn('plain file name', result['message'])


if __name__ == '__main__':
    unittest.main()
