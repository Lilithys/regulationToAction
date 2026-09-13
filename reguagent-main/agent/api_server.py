#!/usr/bin/env python3
"""Minimal stdlib-only JSON HTTP API over CaseStore (T22). No new dependency: uses
http.server directly, matching this project's existing pure-Python-stdlib style.

Every route re-validates by calling the same InvestigationTools/CaseStore methods
the CLI (run_case.py) uses -- a request cannot skip a check by only changing what
the client sends, since the check lives in the shared method, not in this layer.

Single-threaded (HTTPServer, not ThreadingHTTPServer) on purpose: sqlite3
connections in this codebase are opened with check_same_thread's default (True),
so one CaseStore instance is only safe to use from the thread that created it.
This is a two-week prototype's interactive API, not a concurrent production
service; a single persistent connection handling one request at a time is
simpler and correct, where a thread pool would need a connection per thread.
"""
import argparse
import base64
import binascii
import json
import os
import re
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from case_store import CaseStore
from run_case import client_for
from source_intake import open_registered_case
from tool_runtime import RunBudget, ToolRunner
import view_adapter

ROUTES = [
    (re.compile(r'^/api/health$'), 'GET', 'health'),
    (re.compile(r'^/api/cases/start$'), 'POST', 'start'),
    (re.compile(r'^/api/cases$'), 'GET', 'cases'),
    (re.compile(r'^/api/cases/(?P<case_id>[^/]+)$'), 'GET', 'overview'),
    (re.compile(r'^/api/cases/(?P<case_id>[^/]+)/decision-view$'), 'GET', 'decision_view'),
    (re.compile(r'^/api/cases/(?P<case_id>[^/]+)/investigation$'), 'GET', 'investigation'),
    (re.compile(r'^/api/cases/(?P<case_id>[^/]+)/plans$'), 'GET', 'plans'),
    (re.compile(r'^/api/cases/(?P<case_id>[^/]+)/evidence$'), 'GET', 'evidence'),
    (re.compile(r'^/api/cases/(?P<case_id>[^/]+)/evidence$'), 'POST', 'submit_evidence'),
    (re.compile(r'^/api/cases/(?P<case_id>[^/]+)/audit$'), 'GET', 'audit'),
    (re.compile(r'^/api/cases/(?P<case_id>[^/]+)/queue$'), 'GET', 'queue'),
    (re.compile(r'^/api/cases/(?P<case_id>[^/]+)/queue/(?P<item_id>.+)/resolve$'), 'POST', 'resolve'),
    (re.compile(r'^/api/cases/(?P<case_id>[^/]+)/run$'), 'POST', 'run'),
]


def _budget(body):
    values = body.get('budget') or {}
    if not isinstance(values, dict):raise ValueError('budget must be a JSON object')
    allowed = ('max_model_calls','max_tool_calls','max_delegations','max_tokens','max_seconds',
               'max_request_tokens','max_output_tokens','min_request_interval','tokens_per_minute')
    unknown=set(values)-set(allowed)
    if unknown:raise ValueError(f'Unsupported budget field: {sorted(unknown)[0]}')
    return RunBudget(**{key: values[key] for key in allowed if key in values})


def _run_case(store, case_id, body):
    budget=_budget(body)
    case=store.case(case_id)
    result=ToolRunner(store,case_id,client_for(case['mode']),budget).run()
    status_map={'completed':'investigation_complete','waiting':'waiting_for_input','needs_review':'needs_review'}
    if result.get('outcome',{}).get('status') in status_map:
        result['outcome']['status']=status_map[result['outcome']['status']]
    return result


class Handler(BaseHTTPRequestHandler):
    store = None
    artifact_root = None
    replay_only = False

    def log_message(self, fmt, *args):pass

    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', os.environ.get('CORS_ALLOW_ORIGIN', '*'))
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        length = int(self.headers.get('Content-Length', 0) or 0)
        if length < 0 or length > 41_000_000:
            raise ValueError('Request body exceeds the 41 MB limit')
        if length == 0:return {}
        raw = self.rfile.read(length)
        try:return json.loads(raw)
        except json.JSONDecodeError:raise ValueError('Request body is not valid JSON')

    def _dispatch(self, method):
        path = urlparse(self.path).path
        for pattern, route_method, name in ROUTES:
            if route_method != method:continue
            match = pattern.match(path)
            if match:return name, {k: unquote(v) for k, v in match.groupdict().items()}
        return None, None

    def _handle(self, method):
        name, params = self._dispatch(method)
        if name is None:
            self._send(404, dict(error='not_found', message='No matching route'));return
        try:
            if name == 'health':
                self._send(200, dict(status='ok', replay_only=self.replay_only));return
            if name == 'start':
                body=self._read_json_body()
                mode=body.get('mode','replay' if self.replay_only else 'live')
                if mode not in ('live','replay'):raise ValueError('mode must be live or replay')
                if self.replay_only and mode != 'replay':raise PermissionError('This temporary demo supports replay mode only')
                goal=body.get('goal')
                if goal is not None and (not isinstance(goal,str) or not goal.strip()):raise ValueError('goal must be a non-empty string')
                case_id,created=open_registered_case(self.store,goal or 'Investigate the registered ESG regulatory change and produce supported findings; no legal approval.',mode,nonce='api-registered-case')
                result=dict(case_id=case_id,created=created)
                if body.get('run',True):result['run']=_run_case(self.store,case_id,body)
            elif name != 'cases':
                case_id = params['case_id']
                if self.replay_only and method == 'POST' and self.store.case(case_id)['mode'] != 'replay':
                    raise PermissionError('This temporary demo supports replay mode only')
            if name == 'start':pass
            elif name == 'cases':result = view_adapter.case_list(self.store)
            elif name == 'overview':result = view_adapter.case_overview(self.store, case_id)
            elif name == 'decision_view':result = view_adapter.decision_view(self.store, case_id, self.artifact_root)
            elif name == 'investigation':result = view_adapter.investigation_summary(self.store, case_id)
            elif name == 'plans':result = view_adapter.plan_and_action_view(self.store, case_id)
            elif name == 'evidence':result = view_adapter.evidence_view(self.store, case_id)
            elif name == 'audit':result = view_adapter.audit_log(self.store, case_id)
            elif name == 'queue':result = view_adapter.pending_queue(self.store, case_id, self.artifact_root)
            elif name == 'resolve':
                body = self._read_json_body()
                auto_continue=body.pop('auto_continue',False)
                if not isinstance(auto_continue,bool):raise ValueError('auto_continue must be boolean')
                result = view_adapter.resolve_queue_item(self.store, case_id, params['item_id'], body, self.artifact_root)
                if auto_continue:result['continuation']=_run_case(self.store,case_id,body)
            elif name == 'submit_evidence':
                body = self._read_json_body()
                for field in ('action_key', 'evidence_slot', 'evidence_type', 'submitted_by_role_id', 'filename', 'content_base64'):
                    if field not in body:raise ValueError(f'Missing field: {field}')
                raw = base64.b64decode(body['content_base64'], validate=True)
                filename=body['filename']
                if not isinstance(filename,str) or not filename or '/' in filename or '\\' in filename or filename in ('.','..'):
                    raise ValueError('filename must be a plain file name')
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / filename
                    path.write_bytes(raw)
                    submitted = view_adapter.submit_evidence_item(self.store, case_id, body['action_key'],
                        body['evidence_slot'], body['evidence_type'], path, body['submitted_by_role_id'], self.artifact_root)
                result = dict(kind='submit_evidence', result=submitted)
            elif name == 'run':
                body=self._read_json_body()
                result=_run_case(self.store,case_id,body)
            else:
                self._send(404, dict(error='not_found'));return
        except KeyError:
            self._send(404, dict(error='not_found', message='Unknown case or object'));return
        except (ValueError, binascii.Error) as exc:
            self._send(400, dict(error='invalid_request', message=str(exc)));return
        except PermissionError as exc:
            self._send(403, dict(error='forbidden', message=str(exc)));return
        self._send(200, result)

    def do_GET(self):self._handle('GET')
    def do_POST(self):self._handle('POST')

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', os.environ.get('CORS_ALLOW_ORIGIN', '*'))
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Content-Length', '0')
        self.end_headers()


def make_server(db_path, host='127.0.0.1', port=8765, replay_only=False):
    store = CaseStore(db_path)
    handler = type('BoundHandler', (Handler,), dict(store=store, artifact_root=Path(store.path).parent / 'evidence_artifacts', replay_only=replay_only))
    server = HTTPServer((host, port), handler)
    server.case_store = store
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = make_server(args.db, args.host, args.port)
    print(f'Serving on http://{args.host}:{args.port} (db={args.db})')
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        server.case_store.close()
        server.server_close()


if __name__ == '__main__':main()
