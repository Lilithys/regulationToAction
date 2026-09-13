# Regulatory Change-to-Action -- Frontend (v2, wired to the real API)

This replaces the earlier prototype front end (mock `data.js`, five-stage
A/B/C/D pipeline). It is built directly against the real backend in
`agent/api_server.py` and `agent/view_adapter.py`. There is no mock data
anywhere in this version -- every screen calls a real endpoint and shows an
error if that call fails, rather than falling back to fixtures.

## English display

`display_text.js` translates known legacy replay prose when the API client reads
case data, including nested audit details and queue labels. It keeps identifiers,
numbers, dates and unknown text intact. It does not modify the SQLite database,
audit history, or POST payloads. New replay output is English, and the shared live
role prompt also requests English user-facing output. This is a compatibility
catalog for legacy replay text, not a general translation service for user content.

Run the display regression checks from the repository root:

```bash
node --test frontend_v2/tests/display_text.test.js
```

## Known blocker: CORS

`api_server.py`, as currently written, sends no `Access-Control-Allow-Origin`
header. If you serve these frontend files from a different origin/port than
the API (which is the normal way to run a static frontend), **the browser will
block every fetch call before it reaches this code.** This is not a frontend
bug -- it needs a one-line fix on the server side, adding something like:

```python
def _send(self, status, payload):
    body = json.dumps(payload, ensure_ascii=False, default=str).encode('utf-8')
    self.send_response(status)
    self.send_header('Content-Type', 'application/json; charset=utf-8')
    self.send_header('Access-Control-Allow-Origin', '*')   # <-- add this
    self.send_header('Content-Length', str(len(body)))
    self.end_headers()
    self.wfile.write(body)
```

Until that's added server-side, you will see "Network error calling ..." in
the UI even when the API itself is running and reachable.

## Running

1. Start the API server (see the backend's own instructions):
   ```bash
   .venv/bin/python agent/api_server.py --db runs/esg_live.sqlite3 --port 8765
   ```
2. Serve this frontend folder with any static server, e.g.:
   ```bash
   python3 -m http.server 8000
   ```
3. Open `http://localhost:8000`, set the API base URL (defaults to
   `http://127.0.0.1:8765`) and enter a real case ID, then click Load.

## Files

- `index.html` -- shell: case loader bar, tab navigation, content area
- `api.js` -- thin client, one function per route in `api_server.py`'s `ROUTES`
  table. No mock fallback: a failed fetch throws, the UI shows the error.
- `app.js` -- all six views (Overview, Investigation, Plans & Actions,
  Evidence, Queue, Audit Log), each rendered straight from the matching API
  response shape returned by `view_adapter.py`.
- `icons.js` -- inline line-icon SVGs, no external font, no emoji.
- `styles.css` -- black/white/grey minimal design system (unchanged from the
  earlier prototype's visual language).

## Endpoint map

| View | Endpoint |
|---|---|
| Overview | `GET /api/cases/:id` -> `view_adapter.case_overview` |
| Investigation | `GET /api/cases/:id/investigation` -> `view_adapter.investigation_summary` |
| Plans & Actions | `GET /api/cases/:id/plans` -> `view_adapter.plan_and_action_view` |
| Evidence | `GET /api/cases/:id/evidence` -> `view_adapter.evidence_view` |
| Audit Log | `GET /api/cases/:id/audit` -> `view_adapter.audit_log` |
| Queue | `GET /api/cases/:id/queue` -> `view_adapter.pending_queue` |
| (any queue item) | `POST /api/cases/:id/queue/:item_id/resolve` -> `view_adapter.resolve_queue_item` |
| (evidence upload) | `POST /api/cases/:id/evidence` -> `view_adapter.submit_evidence_item` |

## What changed vs. the old prototype, and why

The pending queue in the real backend has **four** sections, not the eight the
old prototype's `data.js` had:

| Section | What it is | What resolving it can do |
|---|---|---|
| `fact` | An open `Question` | Submit an answer |
| `response` | A draft `Action` | **Accept only** -- there is no modify or reject operation on this endpoint |
| `evidence` | Submitted evidence awaiting human review | `verified` or `rejected` -- **no reason field is accepted or required** |
| `closure` | An `Action` where `evaluate_closure` says `can_close` | Close it |

The old prototype's `weight` (AHP pairwise-matrix sign-off), `priority`
(capacity conflict), `detection` (external monitoring intake), and `earlyexit`
sections do not exist in this API. AHP review was demoted to an optional CLI
flag (`--review-ahp`) outside the main case flow; the others are simply not
part of what has been built yet (see the backend's own `TODO.md`).

## One field-level gap that still needs confirming

The `fact` (Question) answer form submits `{ value, source_note }`. This is a
**reasonable guess**, not a verified shape -- the real schema lives in
`ANSWER_SCHEMA` inside `agent/investigation_tools.py`, which was not available
when this frontend was written. If the server rejects an answer submission
with a 400, check that schema and adjust the field names in
`app.js`'s `renderFactForm` function accordingly. This is marked with a
`TODO` comment at the exact line in the code.

## Testing performed

All six views and all four queue-resolution forms were smoke-tested against
mocked API responses shaped exactly like the real endpoints' documented return
values (15/15 checks passed). This confirms the rendering and interaction
logic is correct **given that shape** -- it has not been tested against a
live server with real case data, since the backend requires a populated
SQLite case store this session did not have access to.
